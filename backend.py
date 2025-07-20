from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import os
from openai import OpenAI
from datetime import datetime


app = Flask(__name__)
CORS(app)  # Enable CORS for all routes


# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


if not os.getenv('OPENAI_API_KEY'):
    raise RuntimeError(
        'OPENAI_API_KEY environment variable not set. Please set it to your OpenAI API key.')

# Context provided by the user
guidelines_context = """
Guidelines for Measuring Developer Organization’s Technical Cybersecurity and Privacy Protections Over a Given Algorithm Within a Year of Problem Emergence

BASIC CONCEPTS:
• Pair of algorithms: in this study, we formed pairs of algorithms. Each pair has a “problematic algorithm” and matched “problem-free algorithm.”
• Problematic Algorithm: an algorithm which experienced one or more of the following problems: cybersecurity breach, privacy breach, IT failure.
• Problem-free Algorithm: another algorithm which was very similar to the problematic algorithm in the pair, but it had not experienced any of the cybersecurity, privacy, or IT failure problems experienced by the problematic algorithm in the pair as of the year of problem emergence.
• Year of Problem Emergence: The year in which the problematic algorithm in the pair experienced a problem.
• Developer Organization: the organization which developed a given algorithm.
• Timeframe of measurement of develop organization’s technical cybersecurity and privacy protections over a given algorithm: To delineate cause-and-effect, we will measure the protections one year before the Year of Problem Emergence. For instance, if the year of problem emergence is 2016, please search for evidence of the technical protections from year 2015 to year 2016.

MEASUREMENT of NEWLY ADDED VARIABLES
[200] DevOrgTechCyberProtect
Developer Org’s technical cybersecurity protections for a given AI within a year of problem emergence.
Question: In the year before the Year of Problem Emergence, was there any publicly available evidence that the developer organization have any technical cybersecurity protections over the given algorithm?
Answer choices to select from in the Excel sheet:
• [0]. No evidence that developer org had technical cybersecurity protections for the given AI within a year of the problem emergence year.
• [1]. Symbolic evidence that developer org had technical cybersecurity protections for the given AI within a year of the problem emergence year.
• [2]. Substantive evidence that developer org had technical cybersecurity protections for the given AI within a year of the problem emergence year.

[201] DevOrgTechPrivacyProtect
Developer Org’s technical privacy protections for a given AI in the year of problem emergence
Question: In the year before the Year of Problem Emergence, was there any publicly available evidence that the developer organization had any technical privacy protections over the given algorithm?
Answer choices to select from in the Excel sheet:
• [0]. No evidence that developer org had technical privacy protections for the given AI within a year of the problem emergence year.
• [1]. Symbolic evidence that developer org had technical privacy protections for the given AI within a year of the problem emergence year.
• [2]. Substantive evidence that developer org had technical privacy protections for the given AI within a year of the problem emergence year.

Columns for Justification of Answers and Documentation of Supporting Evidence
Each variable you code will be followed by a justification column and a Source document column.

JUSTIFICATION COLUMNS
- [200a] JustifyDevOrgTechCyberProtect
- [201a] JustifyDevOrgTechPrivacyProtect
Ask you to briefly justify why you selected [0] or [1] or [2] as an answer.
If you selected “[0]. No evidence…” in the justification column next to the measure, please briefly explain how you conducted the searches. A critic may argue that you did not find any evidence of the protection because you did not do the searches properly (e.g., not using the relevant keywords, not searching in the correct timeframe, not checking relevant company websites and documents, etc.). Your explanation should convince a critic that you did the searches with the right keywords, within the right timeframe, and in the right sources (e.g., snapshot of company websites in the WayBack Machine and Google and GenAI searches in the right timeframe, i.e., within a year before the problem emergence year). If you selected [1] or [2], briefly discuss why you selected “[1] Symbolic evidence” rather than “[2] Substantive evidence” or vice versa.

SOURCE DOCUMENT COLUMNS
- [200b] SourceDevOrgTechCyberProtect
- [201b] SourceDevOrgTechPrivacyProtect
Ask you to document the sources in which you found the supporting evidence for your answers.
If no evidence was found, leave the cell blank.
If you found “[1] Symbolic evidence” or “[2] Substantive evidence,” copy and paste the URL in which you saw the evidence.

TIPS FOR IDENTIFYING TECHNICAL CYBERSECURITY PROTECTIONS OVER A GIVEN ALGORITHM:
Algorithms are now the attack surface (the targets) for cybersecurity attacks such as confidentiality attacks, Integrity attacks, and availability attacks. These attacks are known as the C.I.A. triad of cybersecurity. Confidentiality attacks aims to steal sensitive data or intellectual property of an AI model. Integrity attack aims to manipulate the decision outcomes of the AI model. Availability attacks aim to slow down the services of the AI model or make them unavailable to legitimate users. There are many types of cybersecurity attacks on AI and ML systems. MITRE ATLAS Framework keeps a repository of the emerging cyber attack techniques on AI and ML. If available, the framework also discusses protections / mitigations against these attacks. Please familiarize yourself with this framework and the types of cyber attacks on AI:
https://atlas.mitre.org/matrices/ATLAS
Our goal is to assess if the developer organization was using any technical cybersecurity protections within a year before the emergence of the problem to protect the given algorithm against any of these cybersecurity attacks.
"""


def cybersec_prompt(company, algo, year_range, desc=""):
    return f"""
{guidelines_context}

---

**Original Query:**

You are a cybersecurity analyst with access to comprehensive industry knowledge, regulatory filings, news reports, academic research, and company documentation. Analyze the specific cybersecurity protections {company} implemented for its {algo} during {year_range}.


**Analysis Requirements:**
1. Provide concrete, evidence-based assessments rather than generic industry assumptions.
2. Reference specific company announcements, regulatory filings, security incidents, or documented practices.
3. Include actual URLs and sources where this information was documented.
4. Distinguish between confirmed implementations and likely practices.
5. Address specific vulnerabilities relevant to {algo} type systems.


**Research Areas to Investigate:**
- Company security announcements and transparency reports
- Regulatory compliance filings and enforcement actions
- Security incident reports and company responses
- Academic research on the company's security practices
- Congressional testimony or government assessments
- Third-party security audits or certifications
- Patent filings related to security implementations
- Industry reports specifically mentioning the company


**Specific Security Domains to Analyze:**
1. **Data Protection & Encryption**: Documented encryption standards, data residency controls, access segregation.
2. **Access Controls**: Authentication systems, employee access policies, documented access violations.
3. **Algorithm Integrity**: Anti-manipulation measures, adversarial testing, model protection.
4. **Monitoring & Incident Response**: Security monitoring systems, documented incident responses.
5. **Regulatory Compliance**: Specific compliance frameworks, fines, or enforcement actions.
6. **Third-party Security**: External audits, security partnerships, infrastructure providers.


{f'Algorithm Context: {desc}' if desc else ''}


**Output Format (Based on Guidelines):**
For variable [200] DevOrgTechCyberProtect, provide your full analysis, including the code, justification, and sources in a single text block, clearly labeled as requested in the guidelines.

**Code**: [0, 1, or 2]
**Justification**: [JustifyDevOrgTechCyberProtect - Specific evidence with dates, incidents, or documented practices, explaining why you chose 0, 1, or 2]
**Sources**: [SourceDevOrgTechCyberProtect - Actual URLs, document titles, or specific references]

**Additional Requirements:**
- Prioritize company-specific sources over generic industry standards.
- Include both positive security implementations and documented failures/incidents.
- Provide context about why certain protections were implemented (regulatory pressure, incidents, etc.).
- Note any gaps or limitations in available documentation.

Focus on factual, documented evidence rather than assumptions about what the company "would likely" implement.
"""


def privacy_prompt(company, algo, year_range, desc=""):
    return f"""
{guidelines_context}

---

**Original Query:**

Did {company} use any technical privacy enhancing techniques (PETs) to protect the privacy of the data collected and managed by its {algo} in years {year_range}?
Some examples of PETs are differential privacy; federated Learning; homomorphic encryption; secure multi-party computation; synthetic data generation; trusted execution environments; running code in a secure hardware enclave; and machine unlearning.
Search snapshots of {company} websites in {year_range}; include the URLs in which you find relevant evidence; check if there were any academic papers discussing privacy protections of the {algo} in {year_range}
{f'Algorithm description: {desc}' if desc else ''}

**Output Format (Based on Guidelines):**
For variable [201] DevOrgTechPrivacyProtect, provide your full analysis, including the code, justification, and sources in a single text block, clearly labeled as requested in the guidelines.

**Code**: [0, 1, or 2]
**Justification**: [JustifyDevOrgTechPrivacyProtect - Your explanation for why you chose 0, 1, or 2]
**Sources**: [SourceDevOrgTechPrivacyProtect - URLs if any, or 'No sources found']
"""


def gpt_query(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.0,
            max_tokens=800
        )
        print(response.choices[0].message.content)
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"


@app.route('/analyze', methods=['POST', 'OPTIONS'])
def analyze():
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add('Access-Control-Allow-Headers', "*")
        response.headers.add('Access-Control-Allow-Methods', "*")
        return response

    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No JSON data received'}), 400

        company = data.get('company', '').strip()
        algorithm = data.get('algorithm', '').strip()
        description = data.get('description', '').strip()
        year_range = data.get('year_range', '').strip()

        if not all([company, algorithm, year_range]):
            return jsonify({'error': 'Please fill in all required fields.'}), 400

        # Debug log
        print(f"Processing request: {company}, {algorithm}, {year_range}")

        # Cybersecurity
        cybersec_prompt_text = cybersec_prompt(
            company, algorithm, year_range, description)
        cybersec_response = gpt_query(cybersec_prompt_text)

        # Privacy
        privacy_prompt_text = privacy_prompt(
            company, algorithm, year_range, description)
        privacy_response = gpt_query(privacy_prompt_text)

        # Construct the result with the full, unparsed responses
        result = {
            'company': company,
            'algorithm': algorithm,
            'year_range': year_range,
            'cybersecurity': cybersec_response,
            'privacy': privacy_response,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        response = jsonify(result)
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response

    except Exception as e:
        print(f"Error processing request: {str(e)}")  # Debug log
        response = jsonify({'error': f'Server error: {str(e)}'})
        response.headers.add("Access-Control-Allow-Origin", "*")
        return response, 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
