from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import os
import sys  # [NEW] Import the 'sys' module
from datetime import datetime
from dotenv import load_dotenv
import time
import re

from openai import OpenAI
from serpapi import GoogleSearch

# This determines the correct path for the .env file, whether running as a script or as a PyInstaller executable.
if getattr(sys, 'frozen', False):
    # If the application is run as a bundle (frozen), the base path is the directory of the executable
    base_path = os.path.dirname(sys.executable)
else:
    # If run as a normal script, the base path is the script's directory
    base_path = os.path.dirname(os.path.abspath(__file__))

# Construct the full path to the .env file
dotenv_path = os.path.join(base_path, '.env')

# Load the .env file from the explicit path
load_dotenv(dotenv_path=dotenv_path)
# --- End of new block ---


app = Flask(__name__)
CORS(app)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

# This check will now work correctly
if not OPENAI_API_KEY:
    raise RuntimeError(f"Please set OPENAI_API_KEY in your environment. Looked for .env at: {dotenv_path}")
if not SERPAPI_KEY:
    raise RuntimeError(f"Please set SERPAPI_KEY in your environment. Looked for .env at: {dotenv_path}")

client = OpenAI(api_key=OPENAI_API_KEY)


def fetch_urls_comprehensive(base_query, year_range, company, limit_per_query=10):
    """
    Executes a battery of targeted searches to exhaustively cover different
    types of web content, including academic, corporate, and developer sources.
    """
    all_urls = set()  # Use a set to automatically handle duplicates

    # The 'before:' operator is crucial for accurate historical research.
    date_filter = f"before:{year_range}-01-01"
    
    # Sanitize company name for use in URLs (e.g., "Google LLC" -> "google")
    company_domain = company.lower().split(' ')[0].replace(',', '').replace('.', '')

    # Define a list of targeted query templates. Each template has a different goal.
    search_templates = [
        # 1. Core Search: Broad query for general documents and news.
        f'("{company}" OR "{base_query}") ("cybersecurity protections" OR "privacy principles" OR "threat model") {date_filter}',
        
        # 2. Academic & Research Paper Search: Find deep technical documents.
        f'("{company}" OR "{base_query}") (filetype:pdf OR site:arxiv.org OR site:acm.org) {date_filter}',
        
        # 3. Developer & Code Search: Find ground truth in code, READMEs, and developer discussions.
        f'site:github.com/{company_domain} ("{base_query}" OR "security" OR "vulnerability") {date_filter}',
        
        # 4. Official Corporate Search: Find official statements on company-owned domains.
        f'site:{company_domain}.com ("{base_query}" OR "security report" OR "responsible disclosure") {date_filter}',
        
        # 5. Security Community Search: Find discussions on security blogs and vulnerability databases.
        f'("{company}" AND "{base_query}") (intext:"CVE-" OR "security advisory" OR "vulnerability report" OR site:threatpost.com OR site:krebsonsecurity.com) {date_filter}',
        
        # 6. Patent Search: Find early R&D on related security technology.
        f'site:patents.google.com "{company}" "{base_query}" security {date_filter}'
    ]

    for query in search_templates:
        print(f"[INFO] Executing Search Query: {query}")
        search = GoogleSearch({
            "api_key": SERPAPI_KEY,
            "q": query,
            "num": limit_per_query
        })

        try:
            results = search.get_dict().get("organic_results", [])
            urls_from_query = [res.get("link", "") for res in results if "link" in res]
            
            if urls_from_query:
                print(f"[INFO]   => Found {len(urls_from_query)} URLs.")
                all_urls.update(urls_from_query)
            else:
                print(f"[INFO]   => No results for this query.")
                
        except Exception as e:
            print(f"[ERROR] SerpApi search failed for query '{query}': {e}")
            
        time.sleep(1) # Add a small delay between queries to be polite to the API

    print(f"[SUCCESS] Total unique URLs found across all searches: {len(all_urls)}")
    return list(all_urls)


def cybersec_prompt(company, algo, year_range, desc="", urls=None):
    urls_block = ""
    if urls:
        urls_block = "Here are URLs that may help your assessment:\n" + \
            "\n".join(f"- {u}" for u in urls) + "\n\n"

    # [MODIFIED] Added the requested coding scheme to the prompt below.
    return f"""{urls_block}
You are a cybersecurity analyst. Assess whether {company} applied any technical cybersecurity protections for its {algo} on or before {year_range}.
TIPS FOR IDENTIFYING TECHNICAL CYBERSECURITY PROTECTIONS OVER A GIVEN ALGORITHM:
Algorithms are now the attack surface (the targets) for cybersecurity attacks such as confidentiality attacks, Integrity attacks, and availability attacks. 
These attacks are known as the C.I.A. triad of cybersecurity. Confidentiality attacks aims to steal sensitive data or intellectual property of an AI model. 
Integrity attack aims to manipulate the decision outcomes of the AI model. Availability attacks aim to slow down the services of the AI model  or make 
them unavailable to legitimate users. There are many types of cybersecurity attacks on AI  and ML systems. 
MITRE ATLAS Framework keeps a repository of the emerging cyber attack techniques on AI and ML. If available, the framework also discusses protections /
mitigations against these attacks. Please familiarize yourself with this framework and the types of cyber attacks on AI:  
https://atlas.mitre.org/matrices/ATLAS

Treat the URLs above as context, but use your expertise to simulate missing details like publication years or titles. Our goal is to assess if the {company} 
was using any technical cybersecurity protections {year_range} before the emergence of the  problem to protect the given algorithm against any of 
these cybersecurity attacks. dont mention anything irrelevant to {algo} or {company}.mif you find {company} has taken mitigations or is at least aware about the problem, mention accordingly, otherwise dont mention anything irrelevant.

Respond in EXACTLY the following structured format:

---

**[200] DevOrgTechCyberProtect:**  
(Choose ONE: No Evidence, Symbolic Evidence, or Substantive Evidence)
**No Evidence: [0]**
**Symbolic Evidence: [1]**
**Substantive Evidence: [2]**

---

**[200a] JustifyDevOrgTechCyberProtect:**  
- Explain clearly why you selected that level. Analyze all URLs together and simulate missing metadata as needed.
- Consider both specific and {company}-level practices.
- Use URLs retrieved by SerpApi to extract evidence of technical cybersecurity protections. If irrelevant, explicitly note it.
- Also apply your own cybersecurity analyst knowledge to fill gaps — simulate plausible defenses the company may have implemented during the specified 
time (e.g., model integrity checks, access controls, threat modeling, encryption, ML hardening, anomaly detection).
- In your final summary, clearly separate what came from SerpApi links and what was inferred and your own analysis, then synthesize both into a reasoned 
judgment about whether the protections were symbolic, substantive, or absent.

---

**[200b.1] SourceURLsFromSerpApi:**
Only list the URLs directly provided via SerpApi, along with their metadata and relevance assessment.

If a URL is irrelevant or only marginally related, say so clearly in the relevance field.

Example:

URL: https://example.com/page
Title/Snippet: "Document Title"
Year: YYYY
Relevance: Weak or no relevance to {company} or {algo} — retained only as part of SerpApi search results.

**[200b.2] SourceURLsFromAnalystInference:**
Now, based on your own expert knowledge (without using SerpApi URLs), simulate likely or known real-world URLs, reports, or official resources that support your conclusions. Generate realistic-looking URLs only if no better data exists.

Example:

URL: https://about.fb.com/news/2020/fake-accounts
Title/Snippet: "Update on Fake Account Detection"
Year: 2020
Relevance: Facebook official blog directly discussing ML-based protections for its account verification system.

---

Important:
- Always generate 5 to 10 sources.
- Include real or simulated metadata.
- Focus strictly on {company} or its {algo}.
- Do not output anything outside the 3 sections.
- Keep SerpApi URLs and GPT-inferred URLs completely separate.
- Do not blend general knowledge conclusions with SerpApi-derived URLs.
- In [200a], clearly state whether your evidence relied more on actual URLs (from SerpApi) or on expert inference due to lack of strong source URLs.

{f"Algorithm Context: {desc}" if desc else ""}
"""

def privacy_prompt(company, algo, year_range, desc="", urls=None):
    urls_block = ""
    if urls:
        urls_block = "Here are URLs that may help your assessment:\n" + \
            "\n".join(f"- {u}" for u in urls) + "\n\n"

    # [MODIFIED] Added the requested coding scheme to the prompt below.
    return f"""{urls_block}
You are an AI privacy researcher. Assess whether {company} applied any technical privacy protections (PETs) to its {algo} on or before {year_range}.

PETs include Differential Privacy, Federated Learning, Homomorphic Encryption, etc.
TIPS FOR IDENTIFYING TECHNICAL PRIVACY PROTECTIONS OVER A GIVEN ALGORITHM:
An algorithm can leak private data in its training set or any other data it receives during usage. There are various “privacy preservation techniques” (PETs) that developer organizations can use to preserve the privacy of data managed by a given algorithm. Some examples of PETs include:
-   Differential privacy
-   Federated Learning
-   Homomorphic encryption
-   Secure Multi-Party Computation
-   Synthetic Data Generation
-   Trusted Execution Environments
-   Run code in a secure hardware enclave
-   Machine Unlearning

Treat URLs as context. Simulate missing details (year, title) as needed. Our goal is to assess if the developer organization used any technical 
privacy enhancing techniques, 
such as the ones above, to protect privacy of the given {algo}, {year_range} before the emergence of the  problem. dont mention anything irrelevant to {algo} or {company}.
if you find {company} has taken mitigations or is at least aware about the problem, mention accordingly, otherwise dont mention anything irrelevant.

Respond in EXACTLY the following structured format:

---

**[201] DevOrgTechPrivacyProtect:**  
(Choose ONE: No Evidence, Symbolic Evidence, or Substantive Evidence)
**No Evidence: [0]**
**Symbolic Evidence: [1]**
**Substantive Evidence: [2]**

---

**[201a] JustifyDevOrgTechPrivacyProtect:**  
- Explain clearly your assessment. Use company practices and URLs. Simulate missing metadata.
- Consider both specific and {company}-level practices.
- Use URLs retrieved by SerpApi to extract evidence of privacy protections. If irrelevant, explicitly note it.
- Also use your own analyst-level knowledge to fill in gaps — simulate documentation, policies, or techniques realistically used during the specified 
time range.
- In your final summary, clearly distinguish which insights came from SerpApi URLs and which were inferred. Then synthesize both - urls from serpai 
and your own analysis into a coherent judgment on whether substantive/symbolic/no privacy protections were applied to the {algo} or {company} systems.

---

**[201b.1] SourceURLsFromSerpApi:**
Only list the URLs directly provided via SerpApi, along with their metadata and relevance assessment.

If a URL is irrelevant or only marginally related, say so clearly in the relevance field.

Example:

URL: https://example.com/page
Title/Snippet: "Document Title"
Year: YYYY
Relevance: Weak or no relevance to {company} or {algo} — retained only as part of SerpApi search results.

**[201b.2] SourceURLsFromAnalystInference:**
Now, based on your own expert knowledge (without using SerpApi URLs), simulate likely or known real-world URLs, reports, or official resources that support your conclusions. Generate realistic-looking URLs only if no better data exists.

Example:

URL: https://about.fb.com/news/2020/fake-accounts
Title/Snippet: "Update on Fake Account Detection"
Year: 2020
Relevance: Facebook official blog directly discussing ML-based protections for its account verification system.

---

Important:
- Always generate 5 to 10 sources.
- Include real or simulated metadata.
- Focus strictly on {company} or its {algo}.
- Do not output anything outside the 3 sections.
- Keep SerpApi URLs and GPT-inferred URLs completely separate.
- Do not blend general knowledge conclusions with SerpApi-derived URLs.
- In [200a], clearly state whether your evidence relied more on actual URLs (from SerpApi) or on expert inference due to lack of strong source URLs.

{f"Algorithm Context: {desc}" if desc else ""}
"""


def gpt_query(prompt):
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=1.0,
        max_tokens=2000,
    )
    return resp.choices[0].message.content


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

    # Create focused base queries for cybersecurity and privacy
    cs_base_query = f'"{algo}" cybersecurity'
    pr_base_query = f'"{algo}" privacy'

    # Use the new comprehensive search function for both topics.
    print("[INFO] Starting comprehensive URL fetch for Cybersecurity...")
    cs_urls = fetch_urls_comprehensive(cs_base_query, year_range, company)

    print("\n[INFO] Starting comprehensive URL fetch for Privacy...")
    pr_urls = fetch_urls_comprehensive(pr_base_query, year_range, company)

    # Combine the lists and de-duplicate for the prompts, as there can be overlap
    # We can pass a unified list of all discovered URLs to both prompts
    combined_urls = list(set(cs_urls + pr_urls))
    print(f"\n[INFO] Total unique URLs for analysis: {len(combined_urls)}")

    cs_prompt = cybersec_prompt(company, algo, year_range, desc, combined_urls)
    pr_prompt = privacy_prompt(company, algo, year_range, desc, combined_urls)

    cs_answer = gpt_query(cs_prompt)
    pr_answer = gpt_query(pr_prompt)

    return jsonify({
        "company": company,
        "algorithm": algo,
        "year_range": year_range,
        "cybersecurity": cs_answer,
        "privacy": pr_answer,
        "searched_urls": {
            "cybersec": cs_urls, # You can still see which came from which search
            "privacy": pr_urls,
            "combined": combined_urls
        },
        "timestamp": datetime.utcnow().isoformat()
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)