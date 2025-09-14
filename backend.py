from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import os
import sys
import time
from datetime import datetime, UTC  # Import UTC
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from openai import OpenAI
from serpapi import GoogleSearch
import string

# Optional: For more accurate token counting
try:
    import tiktoken
except ImportError:
    print("[WARNING] tiktoken not installed. Install with `pip install tiktoken` for accurate token counting.")
    tiktoken = None


if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

dotenv_path = os.path.join(base_path, '.env')
load_dotenv(dotenv_path=dotenv_path)

app = Flask(__name__)
CORS(app)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")


OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_MAX_COMPLETION_TOKENS = int(os.getenv(
    "OPENAI_MAX_COMPLETION_TOKENS", "4000"))


MODEL_CONTEXT_WINDOW = 128000

if not OPENAI_API_KEY:
    raise RuntimeError(
        f"Please set OPENAI_API_KEY in your environment. Looked for .env at: {dotenv_path}")
if not SERPAPI_KEY:
    raise RuntimeError(
        f"Please set SERPAPI_KEY in your environment. Looked for .env at: {dotenv_path}")

client = OpenAI(api_key=OPENAI_API_KEY)

# ----------------------------
# SerpApi comprehensive search (no date filter)
# ----------------------------


def fetch_urls_comprehensive(base_query, year_range, company, limit_per_query=10):
    all_urls = set()

    # Robust domain token extraction: first word, lowercase, strip punctuation
    first_token = company.strip().split()[0].lower() if company.strip() else ""
    company_domain = first_token.translate(
        str.maketrans("", "", string.punctuation))

    search_templates = [
        f'("{company}" OR "{base_query}") ("cybersecurity protections" OR "privacy principles" OR "threat model")',
        f'("{company}" OR "{base_query}") (filetype:pdf OR site:arxiv.org OR site:acm.org)',
        f'site:github.com/{company_domain} ("{base_query}" OR "security" OR "vulnerability")' if company_domain else f'("{base_query}" OR "security" OR "vulnerability") site:github.com',
        f'site:{company_domain}.com ("{base_query}" OR "security report" OR "responsible disclosure")' if company_domain else f'("{base_query}" OR "security report" OR "responsible disclosure")',
        f'("{company}" AND "{base_query}") (intext:"CVE-" OR "security advisory" OR "vulnerability report" OR site:threatpost.com OR site:krebsonsecurity.com)',
        f'site:patents.google.com "{company}" "{base_query}" security'
    ]

    for query in search_templates:
        print(f"[INFO] Executing Search Query: {query}")
        search = GoogleSearch(
            {"api_key": SERPAPI_KEY, "q": query, "num": limit_per_query})
        try:
            results = search.get_dict().get("organic_results", [])
            urls_from_query = [r.get("link") for r in results if isinstance(
                r, dict) and r.get("link")]
            if urls_from_query:
                print(f"[INFO]   => Found {len(urls_from_query)} URLs.")
                all_urls.update(urls_from_query)
            else:
                print(f"[INFO]   => No results for this query.")
        except Exception as e:
            print(f"[ERROR] SerpApi search failed for query '{query}': {e}")
        time.sleep(1)

    print(
        f"[SUCCESS] Total unique URLs found across all searches: {len(all_urls)}")
    return list(all_urls)

# ----------------------------
# Robust Wayback CDX windowed check (with retries/backoff)
# ----------------------------


def _make_retrying_session(total_retries=4, backoff_factor=0.9, status_forcelist=(500, 502, 503, 504)):
    sess = requests.Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,  # exponential backoff
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(
        max_retries=retry, pool_connections=10, pool_maxsize=10)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    # Reasonable UA helps reduce blocking
    sess.headers.update(
        {"User-Agent": "cybersec-research/1.0 (+https://example.org)"})
    return sess


def wayback_check_urls_cdx(urls, cutoff_year):
    meta = {}
    try:
        cutoff = int(cutoff_year)
        if not (1996 <= cutoff <= datetime.now().year + 1):  # Sanity check for cutoff year
            raise ValueError("Cutoff year out of reasonable range.")
    except Exception as e:
        for u in urls:
            meta[u] = {"valid": False, "snapshot_year": None,
                       "error": f"Invalid cutoff year: {e}"}
        return meta

    end_year = cutoff - 1   # Inclusive end for the new window

    # Start year: to maintain a 5-year window ending at 'end_year'
    start_year_for_window = end_year - 5  # e.g., if end_year=2017, start_year=2012

    from_ts = f"{start_year_for_window}0101000000"  # Add time for precision
    to_ts = f"{end_year}1231235959"   # Add time for precision

    base = "https://web.archive.org/cdx/search/cdx"
    print(f"[INFO] Wayback CDX range: {from_ts} to {to_ts}")

    session = _make_retrying_session(total_retries=4, backoff_factor=0.9)
    per_request_timeout = 25 
    pause_between_calls = 0.35 
    last_call = 0.0

    for idx, u in enumerate(urls, start=1):
        try:
            # Mild pacing
            elapsed = time.time() - last_call
            if elapsed < pause_between_calls:
                time.sleep(pause_between_calls - elapsed)

            params = {
                "url": u,
                "from": from_ts,
                "to": to_ts,
                "output": "json",
                "filter": "statuscode:200",
                "fastLatest": "true",
                "limit": "1",
            }
            resp = session.get(base, params=params,
                               timeout=per_request_timeout)
            last_call = time.time()

            if resp.status_code == 429:
                print(
                    f"[WARNING] Rate limited by Wayback CDX for {u}. Retrying will occur.")
                meta[u] = {"valid": False, "snapshot_year": None,
                           "error": f"CDX Rate Limit ({resp.status_code})"}
                continue  # Let retry mechanism handle it or mark as error for this pass

            if resp.status_code >= 500:
                meta[u] = {"valid": False, "snapshot_year": None,
                           "error": f"CDX Server Error ({resp.status_code})"}
                continue

            try:
                data = resp.json()
            except Exception:
                meta[u] = {"valid": False, "snapshot_year": None,
                           "error": f"Non-JSON response: {resp.text[:200]}"}
                continue

            if len(data) > 1 and isinstance(data[1], list) and len(data[1]) > 1:
                latest_capture = data[1]
                # Timestamp is typically the second element
                ts = latest_capture[1]
                snap_year = int(ts[:4]) if ts and len(ts) >= 4 else None

                # Check validity against the new window
                is_valid = (
                    snap_year is not None and start_year_for_window <= snap_year <= end_year)
                meta[u] = {"valid": is_valid, "snapshot_year": snap_year}
            else:
                meta[u] = {"valid": False, "snapshot_year": None}

        except requests.exceptions.ReadTimeout as e:
            meta[u] = {"valid": False, "snapshot_year": None,
                       "error": f"Read timeout: {e}"}
        except requests.exceptions.ConnectTimeout as e:
            meta[u] = {"valid": False, "snapshot_year": None,
                       "error": f"Connect timeout: {e}"}
        except requests.exceptions.ConnectionError as e:
            meta[u] = {"valid": False, "snapshot_year": None,
                       "error": f"Connection error: {e}"}
        except Exception as e:
            meta[u] = {"valid": False, "snapshot_year": None, "error": str(e)}

    return meta


def cybersec_prompt(company, algo, year, desc="", urls_and_wayback_meta=None):  # Changed argument
    urls_block = ""

    if urls_and_wayback_meta and isinstance(urls_and_wayback_meta, dict):
        sorted_urls_with_meta = sorted(urls_and_wayback_meta.items(
        ), key=lambda item: item[1].get("valid", False), reverse=True)

        selected_urls_for_prompt = []
        for u, meta in sorted_urls_with_meta:
            selected_urls_for_prompt.append(
                f"- {u} (Wayback year: {meta.get('snapshot_year', 'N/A')}, Valid for period: {meta.get('valid', False)})")
            if len(selected_urls_for_prompt) >= 15:
                break

        if selected_urls_for_prompt:
            urls_block = "Here are up to 15 URLs (prioritizing those with valid Wayback snapshots from before the cutoff) that may help your assessment:\n" + "\n".join(
                selected_urls_for_prompt) + "\n\n"
        else:
            urls_block = "No relevant URLs found within the specified Wayback window to assist the assessment.\n\n"
    elif urls_and_wayback_meta and isinstance(urls_and_wayback_meta, list):
        selected_urls = urls_and_wayback_meta[:15]  # Just take the first 15
        if selected_urls:
            urls_block = "Here are up to 15 URLs that may help your assessment:\n" + \
                "\n".join(f"- {u}" for u in selected_urls) + "\n\n"
        else:
            urls_block = "No URLs provided to assist the assessment.\n\n"

    return f"""{urls_block}
You are a cybersecurity analyst. Assess whether {company} applied any technical cybersecurity protections for its {algo} on or before {year}. Focus strictly on {company}/{algo}. Produce a concise answer in the exact structured format below.

---
** DevOrgTechCyberProtect:**  
Assign the code according to the following:
No Evidence: [0]
Symbolic Evidence: [1]
Substantive Evidence: [2]

**[200a] JustifyDevOrgTechCyberProtect:**  
- Explain clearly why you selected that level. Analyze all provided URLs together and simulate missing metadata as needed.
- Consider both specific and {company}-level practices.
- Use the provided URLs (especially those with valid Wayback snapshots) to extract evidence of technical cybersecurity protections. If a URL is irrelevant or invalid for the time period, explicitly note it.
- Also apply your own cybersecurity analyst knowledge to fill gaps — simulate plausible defenses during the specified time (e.g., model integrity checks, access controls, encryption, anomaly detection).
- In your final summary, clearly separate what came from provided links and what was inferred by your own analysis, then synthesize both into a reasoned judgment.

**[200b.1] SourceURLsFromSerpApi:**
Only list the URLs directly provided above that were deemed relevant by your analysis and had valid Wayback snapshots for the period. Include their associated Wayback year if available.
**[200b.2] SourceURLsFromAnalystInference:**
List simulated or known URLs supporting your conclusions.

{f"Algorithm Context: {desc}" if desc else ""}"""


def privacy_prompt(company, algo, year, desc="", urls_and_wayback_meta=None):  # Changed argument
    urls_block = ""

    if urls_and_wayback_meta and isinstance(urls_and_wayback_meta, dict):
        sorted_urls_with_meta = sorted(urls_and_wayback_meta.items(
        ), key=lambda item: item[1].get("valid", False), reverse=True)

        selected_urls_for_prompt = []
        for u, meta in sorted_urls_with_meta:
            selected_urls_for_prompt.append(
                f"- {u} (Wayback year: {meta.get('snapshot_year', 'N/A')}, Valid for period: {meta.get('valid', False)})")
            if len(selected_urls_for_prompt) >= 15:  # Limit to 15 URLs for prompt
                break

        if selected_urls_for_prompt:
            urls_block = "Here are up to 15 URLs (prioritizing those with valid Wayback snapshots from before the cutoff) that may help your assessment:\n" + "\n".join(
                selected_urls_for_prompt) + "\n\n"
        else:
            urls_block = "No relevant URLs found within the specified Wayback window to assist the assessment.\n\n"
    elif urls_and_wayback_meta and isinstance(urls_and_wayback_meta, list):
        selected_urls = urls_and_wayback_meta[:15]
        if selected_urls:
            urls_block = "Here are up to 15 URLs that may help your assessment:\n" + \
                "\n".join(f"- {u}" for u in selected_urls) + "\n\n"
        else:
            urls_block = "No URLs provided to assist the assessment.\n\n"

    return f"""{urls_block}
You are an AI privacy researcher. Assess whether {company} applied any technical privacy protections (PETs) to its {algo} on or before {year}. Focus strictly on {company}/{algo}. Produce a concise answer in the exact structured format below.


** DevOrgTechPrivacyProtect:**  
Assign the code according to the following:
No Evidence: [0]
Symbolic Evidence: [1]
Substantive Evidence: [2]

**[201a] JustifyDevOrgTechPrivacyProtect:**  
- Explain clearly your assessment. Use company practices and provided URLs. Simulate missing metadata.
- Consider both specific and {company}-level practices.
- Use the provided URLs (especially those with valid Wayback snapshots) to extract evidence of privacy protections. If a URL is irrelevant or invalid for the time period, explicitly note it.
- Also use your own analyst-level knowledge to fill gaps — simulate documentation or techniques likely used.
- Clearly distinguish which insights came from provided URLs vs. inference, then synthesize both into a coherent judgment.

**[201b.1] SourceURLsFromSerpApi:**
Only list the URLs directly provided above that were deemed relevant by your analysis and had valid Wayback snapshots for the period. Include their associated Wayback year if available.
**[201b.2] SourceURLsFromAnalystInference:**
List simulated or known URLS supporting your conclusions.

{f"Algorithm Context: {desc}" if desc else ""}"""




def gpt_query(prompt, model_name=None, max_out=None):
    m = model_name or OPENAI_MODEL
    o = OPENAI_MAX_COMPLETION_TOKENS if max_out is None else max_out

    current_model_context_window = MODEL_CONTEXT_WINDOW

    if tiktoken:
        try:
            encoding = tiktoken.encoding_for_model(m)
        except KeyError:
            print(
                f"[WARNING] Model '{m}' not found in tiktoken; using 'cl100k_base' encoding for token count.")
            encoding = tiktoken.get_encoding("cl100k_base")

        prompt_tokens = len(encoding.encode(prompt))
        print(f"[INFO] Prompt token count: {prompt_tokens}")

        if prompt_tokens + o > current_model_context_window:
            print(
                f"[WARNING] Prompt ({prompt_tokens} tokens) + max_out ({o} tokens) exceeds model context window ({current_model_context_window}). Adjusting max_out.")
            o = current_model_context_window - prompt_tokens - \
                200
            if o < 100:
                o = 100
                print(
                    f"[WARNING] max_out drastically reduced to {o} tokens due to very long prompt after truncation.")
            print(f"[INFO] New max_out: {o}")
    else:
        char_count = len(prompt)
        estimated_tokens = char_count // 4
        print(
            f"[INFO] Estimated prompt token count (chars/4): {estimated_tokens}")
        if estimated_tokens + o > current_model_context_window * 0.75:
            print(
                f"[WARNING] Estimated tokens ({estimated_tokens}) + max_out ({o}) likely exceeds model context window. Consider installing tiktoken or reducing prompt content.")
            # Still attempt to reduce max_out based on estimate
            o = max(100, int(current_model_context_window * 0.75) -
                    estimated_tokens - 200)
            print(f"[INFO] Reduced max_out to: {o}")

    print("*"*50)
    print("Length of prompt (chars)=", len(prompt))
    print("OpenAI Model=", m)
    print("Max completion tokens=", o)
    print("*"*50)

    try:
        r = client.chat.completions.create(
            model=m,
            messages=[{"role": "user", "content": prompt}],
        )
        chs = getattr(r, "choices", None)
        if not chs or len(chs) == 0:
            return None, "No choices returned from model."
        c0 = chs[0]
        msg = getattr(c0, "message", None)
        if not msg:
            return None, "First choice has no message."
        txt = (getattr(msg, "content", "") or "").strip()
        print("$"*10)
        print(txt)
        if txt:
            return txt, None
        fr = getattr(c0, "finish_reason", None)
        return f"[No content returned; finish_reason={fr}]", None
    except Exception as e:
        print(f"[ERROR] OpenAI API call failed: {e}")
        return None, str(e)


# ----------------------------
# Flask route
# ----------------------------
@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    if request.method == "OPTIONS":
        resp = make_response()
        resp.headers.update({
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "*"
        })
        return resp

    data = request.get_json(force=True)
    company = data.get("company", "").strip()
    algo = data.get("algorithm", "").strip()
    desc = data.get("description", "").strip()
    year_range = data.get("year_range", "").strip()

    if not (company and algo and year_range):
        return jsonify(error="company, algorithm, and year_range are required"), 400

    cs_base_query = f'"{algo}" cybersecurity'
    pr_base_query = f'"{algo}" privacy'

    print("[INFO] Starting comprehensive URL fetch for Cybersecurity...")
    cs_urls = fetch_urls_comprehensive(cs_base_query, year_range, company)

    print("[INFO] Starting comprehensive URL fetch for Privacy...")
    pr_urls = fetch_urls_comprehensive(pr_base_query, year_range, company)

    combined_urls = list(set(cs_urls + pr_urls))
    print(f"[INFO] Total unique URLs for analysis: {len(combined_urls)}")

    wayback_metadata = wayback_check_urls_cdx(combined_urls, year_range)
    valid_count = sum(1 for v in wayback_metadata.values() if v.get("valid"))
    invalid_count = len(wayback_metadata) - valid_count
    print(
        f"[INFO] Wayback CDX check completed. Valid in window: {valid_count}, Outside window/none: {invalid_count}")

    cs_prompt = cybersec_prompt(
        company, algo, year_range, desc, wayback_metadata)  # Pass metadata
    pr_prompt = privacy_prompt(
        company, algo, year_range, desc, wayback_metadata)  # Pass metadata

    # GPT calls with try/except
    cyber_txt, cyber_err = gpt_query(cs_prompt)
    privacy_txt, privacy_err = gpt_query(pr_prompt)

    resp_body = {
        "company": company,
        "algorithm": algo,
        "year_range": year_range,
        "cybersecurity": cyber_txt if cyber_err is None else f"[ERROR] {cyber_err}",
        "privacy": privacy_txt if privacy_err is None else f"[ERROR] {privacy_err}",
        "searched_urls": {
            "cybersec": cs_urls,
            "privacy": pr_urls,
            "combined": combined_urls
        },
        # { url: { valid: bool, snapshot_year: int|null, error?: str } }
        "wayback_metadata": wayback_metadata,
        # Corrected deprecation warning
        "timestamp": datetime.now(UTC).isoformat()
    }

    status = 200 if (cyber_err is None and privacy_err is None) else 502
    return jsonify(resp_body), status


if __name__ == "__main__":
    # In production, serve with a production WSGI server and disable debug
    app.run(host="0.0.0.0", port=5000, debug=True)
