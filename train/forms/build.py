"""Generate train/forms/<family>/<variant>/{index.html,meta.json} and train/eval/split.json.

Usage: python3 train/forms/build.py        (idempotent; rewrites every generated file)

Every page is self-contained (inline CSS + inline _runtime.js, no network). Expected values come from
PERSONAS below; each fact carries the literal text it is taken from in the persona's context file, and the
build fails if that text is missing from the context (keeps meta.json and contexts in sync).
A field whose fact is absent from the persona is *infeasible*: expected null, must stay empty.

Besides the hand-written personas, personas.py generates many more per family (deterministic, seed from
FF_PERSONA_SEED, default 1). They are written to train/contexts/<family>/<id>.md and every persona gets
train/contexts/<id>.expected.json with its expected values per variant (see train/docs/forms-catalog.md).
Requires Python >= 3.12.
"""
from __future__ import annotations

import html
import json
import os
import random
import shutil
from pathlib import Path

import personas as gen

HERE = Path(__file__).resolve().parent
TRAIN = HERE.parent
RUNTIME = (HERE / "_runtime.js").read_text()
TODAY = "2026-11-11"
E = html.escape
SEED = int(os.environ.get("FF_PERSONA_SEED", "1"))
GENERATED, RUN = gen.generate(SEED)


# ----------------------------------------------------------------------------------------------
# Personas: fact -> value | (value, source_text) | ([value, *accepted_alternates], source_text)
# Choice facts use option values. Missing fact = infeasible. "" = must stay empty.
# ----------------------------------------------------------------------------------------------
PERSONAS: dict[str, dict] = {
    "emp-huang-yiting": {
        "first_name": "Yi-Ting", "last_name": "Huang", "middle_name": ("", "Middle name | — (none)"),
        "full_name": (["Yi-Ting Huang", "Huang Yi-Ting"], "Yi-Ting Huang"), "employee_id": "KST-20417",
        "dob": ("1993-08-17", "17 August 1993"), "gender": ("female", "Female"), "marital": ("single", "Single"),
        "nationality": ("TW", "Taiwan (R.O.C.)"), "email": "yiting.huang@kestrel-semi.example",
        "mobile": "+886 912 408 337", "create_login": (True, "System username to create"),
        "username": "yiting.huang", "login_status": ("enabled", "Enabled"),
        "requested_for": ("u_huang_yt", "Yi-Ting Huang"), "laptop_model": ("eng16", 'Engineering Workstation Laptop 16"'),
        "location": ("hsp_fab3", "Hsinchu Science Park — Fab 3"), "needed_by": "2026-11-28",
        "justification": ("New hire, Fab Engineering — runs yield analysis tooling (JMP, Python).",
                          "New hire, Fab Engineering — runs yield analysis tooling (JMP, Python)."),
        "extra_monitor": (False, "Extra monitor: not requested"), "cost_center": "CC-3120",
        "department": ("fab_eng", "Fab Engineering"), "session": ("or_dec02_am", "Wednesday 2 December 2026, morning"),
        "attendance": ("in_person", "In person"), "dietary": ("none", "Dietary requirement: none"),
        "tshirt": ("S", "T-shirt size: S"), "recording": (False, "Course recording: not needed"),
        "course": ("orientation", "New-Hire Orientation"),
        "job_title": ("process_int_eng", "Process Integration Engineer"), "work_location": ("hsp_fab3", "Hsinchu Science Park — Fab 3"),
        "emp_status": ("ft_perm", "Full-Time Permanent"), "supervisor": ("u_chen_wl", "Chen Wei-Lun"), "joined_date": ("2026-12-01", "1 December 2026"),
    },
    "emp-okafor-daniel": {
        "first_name": "Daniel", "middle_name": "Chukwuemeka", "last_name": "Okafor",
        "full_name": (["Daniel Okafor", "Daniel Chukwuemeka Okafor"], "Daniel Chukwuemeka Okafor"),
        "employee_id": "KST-11862", "email": "daniel.okafor@kestrel-semi.example", "mobile": "+886 978 115 260",
        "department": ("infosec", "Information Security"),
        "leave_type": ("annual", "Annual Leave"), "leave_from": ("2026-12-28", "28 December 2026"),
        "leave_to": ("2026-12-31", "31 December 2026"), "partial_days": ("end", "the last day (31 December) is a half day"),
        "end_duration": ("half_am", "morning only"),
        "leave_comment": ("Family travel — handover to Ivy Chang for SOC on-call", "Family travel — handover to Ivy Chang for SOC on-call"),
        "caller": ("u_okafor_d", "Daniel Chukwuemeka Okafor"), "inc_category": ("network", "Category: Network"),
        "inc_subcategory": ("vpn", "Subcategory: VPN"), "ci": ("KST-NB-30982", "KST-NB-30982"),
        "impact": ("2", "Impact: 2 - Medium"), "urgency": ("2", "Urgency: 2 - Medium"),
        "contact_pref": ("email", "Contact preference: Email"), "assign_group": ("netops", "Assignment group: Network Operations"),
        "short_desc": "GlobalConnect VPN client fails to connect after 6.2 update",
        "inc_desc": ("Since the 6.2 client update on 10 Nov 2026 the VPN client shows error 809 at login. Happens on office Wi-Fi and home network. Reinstalling did not help.",
                     "Since the 6.2 client update on 10 Nov 2026 the VPN client shows error 809 at login."),
        "course": ("secure_coding", "Secure Coding Workshop"), "session": ("sc_dec09_pm", "Wednesday 9 December 2026, afternoon (13:30–17:00)"),
        "attendance": ("in_person", "In person (Taipei HQ)"), "dietary": ("vegetarian", "Dietary requirement: Vegetarian"),
        "tshirt": ("L", "T-shirt size: L"), "recording": (True, "Wants the course recording: yes"),
        "topics": ("Threat modeling for internal tools; secrets handling in CI", "Threat modeling for internal tools; secrets handling in CI"),
    },
    "patient-lin-chunhua": {
        "first_name": "Chun-Hua", "last_name": "Lin", "middle_name": ("", "Middle name: none"),
        "dob": ("1958-11-03", "03 Nov 1958"), "sex": ("female", "Sex: Female"), "marital": ("widowed", "Widowed"),
        "language": ("mandarin", "Preferred language: Mandarin"),
        "street": "4F, No. 12, Ln. 56, Sec. 6, Minquan E. Rd., Neihu Dist.", "city": "Taipei City", "postal": "114",
        "country": ("TW", "Country: Taiwan"), "phone_home": "02-2793-5512", "phone_cell": "0933-218-604",
        "email": ("", "patient has no email address — leave blank"), "occupation": (["Retired teacher", "Retired"], "Retired teacher"),
        "employer": ("", "Employer: none (retired)"), "ec_name": "Lin Kuan-Yu", "ec_phone": "0921-664-097",
        "ec_relationship": ("child", "relationship: Child"), "ins_provider": ("fmh", "Formosa Mutual Health"),
        "policy_number": "FMH-7730-2214", "group_number": "G-5521", "subscriber_rel": ("self", "Subscriber: Self"),
        "ins_effective": ("2024-01-01", "01 Jan 2024"),
    },
    "kyc-tsai-minghan": {
        "full_name": (["Tsai Ming-Han", "Ming-Han Tsai"], "Tsai Ming-Han"), "spouse_name": "Wu Hsin-Yi",
        "gender": ("male", "Gender: Male"), "marital": ("married", "Marital status: Married"), "dob": ("1981-05-30", "30 May 1981"),
        "nationality": ("TW", "Nationality: Taiwan"), "residency": ("resident", "Resident individual"),
        "tax_id": ("F128473650", "use the national ID F128473650"), "id_proof": ("national_id", "Identity proof provided: national ID card"),
        "phone": "+886 935 662 071", "email": "minghan.tsai@inbox.example",
        "address": (["No. 5, Aly. 3, Ln. 120, Sec. 1, Neihu Rd., Neihu Dist., Taipei City 114, Taiwan",
                     "No. 5, Aly. 3, Ln. 120, Sec. 1, Neihu Rd., Neihu Dist., Taipei City 114"],
                    "No. 5, Aly. 3, Ln. 120, Sec. 1, Neihu Rd., Neihu Dist., Taipei City 114, Taiwan"),
        "perm_same": (True, "Permanent address: same as correspondence address"),
        "addr_proof": ("utility_bill", "utility bill"), "application_no": "LCB-AO-2026-77310",
        "sign_date": ("2026-11-06", "Applicant signing date: 2026-11-06"),
        "decl_name": (["Tsai Ming-Han", "Ming-Han Tsai"], "Tsai Ming-Han"),
        "account_type": ("savings", "Account type: Savings"), "account_category": ("individual", "Account category: Individual"),
        "education": ("master", "Master's degree"), "monthly_income": ("185000", "TWD 185,000"),
        "id_form": ("national_id", "Form of identification for the account: National ID card"),
        "mother_maiden": ("", "Mother's maiden name: NOT collected in writing"),
    },
    "kyc-rivera-sofia": {
        "first_name": "Sofia", "last_name": "Rivera", "street": "2418 Alder Creek Way", "city": "San Jose",
        "state": (["CA", "California"], "San Jose, CA 95131"), "zip": "95131", "phone": "(408) 555-0162", "ssn": "912-48-3307",
        "username": "sofia.rivera89",
        "payee_name": "Bayline Utilities", "payee_street": "500 Market Plaza, Suite 210", "payee_city": ("San Jose", "San Jose, CA 95113"),
        "payee_state": (["CA", "California"], "San Jose, CA 95113"), "payee_zip": "95113", "payee_phone": "(408) 555-0110",
        "payee_account": "77104-2219", "payee_account_verify": ("77104-2219", "77104-2219"), "amount": ("142.67", "$142.67"),
        "from_account": ("13344", "Pay from account: 13344"), "loan_amount": ("25000", "$25,000"),
        "down_payment": ("2500", "$2,500"), "loan_from_account": ("13566", "funded from account 13566"),
        "new_account_type": ("SAVINGS", "type SAVINGS"), "new_account_from": ("13344", "initial funding from account 13344"),
    },
    "vendor-dingfeng": {
        "vendor_name_zh": "鼎峰精密工業股份有限公司", "vendor_name_en": "Dingfeng Precision Industrial Co., Ltd.",
        "org_name": (["Dingfeng Precision Industrial Co., Ltd.", "鼎峰精密工業股份有限公司"], "Dingfeng Precision Industrial Co., Ltd."),
        "ubn": "62527601", "tax_id": ("62527601", "62527601"), "owner": "林志豪", "established": ("2009-06-15", "民國98年6月15日（2009-06-15）"),
        "capital": ("48000000", "NT$48,000,000"), "org_type": ("corp_shares", "股份有限公司"),
        "county": ("新竹縣", "新竹縣竹北市"), "district": ("竹北市", "新竹縣竹北市"), "address_line": ("光明六路16號8樓", "光明六路16號8樓"),
        "postal": ("302", "302 新竹縣"), "tel": "03-558-2216", "fax": "03-558-2219",
        "company_address": (["302 新竹縣竹北市光明六路16號8樓", "8F., No. 16, Guangming 6th Rd., Zhubei City, Hsinchu County 302"], "302 新竹縣竹北市光明六路16號8樓"),
        "contact_name": (["陳雅琪", "Chen Ya-Chi"], "陳雅琪"), "contact_title": ("業務經理", "業務經理"),
        "email": "yachi.chen@dingfeng-precision.example", "contact_mobile": "0918-552-307", "phone_day": ("03-558-2216", "03-558-2216"),
        "bank_code": ("812", "銀行代碼 812"), "account_number": ("20880100456789", "20880100456789"), "bank_branch": (["竹北分行", "竹北"], "竹北分行"), "account_no": "20880100456789",
        "account_name": "鼎峰精密工業股份有限公司", "bank_name": (["台新國際商業銀行", "Taishin International Bank"], "台新國際商業銀行"),
        "beneficiary": (["鼎峰精密工業股份有限公司", "Dingfeng Precision Industrial Co., Ltd."], "戶名：鼎峰精密工業股份有限公司"),
        "payment_terms": ("net60", "月結 60 天"), "invoice_type": ("egui3", "電子發票（三聯式）"), "currency": ("TWD", "新台幣 TWD"),
        "iso9001": (True, "ISO 9001：有"), "iso_expiry": ("2027-03-31", "證書到期日 2027-03-31"), "foreign": (False, "302 新竹縣"),
        "services": (["CNC 精密加工零件、治具製作", "CNC precision machined parts and fixtures"], "CNC 精密加工零件、治具製作"),
        "business_type": ("corporation", "股份有限公司"), "insurance": ("insured", "產品責任保險：有投保"),
        "gross_sales": ("215000000", "約 NT$215,000,000"),
    },
    "vendor-harborline": {
        "org_name": "Harborline Freight Pte. Ltd.", "vendor_name_en": ("Harborline Freight Pte. Ltd.", "Harborline Freight Pte. Ltd."),
        "tax_id": ("201734562K", "Registration (UEN): 201734562K"),
        "company_address": "18 Pioneer Crescent, #05-11, Singapore 628559", "foreign_address": ("18 Pioneer Crescent, #05-11, Singapore 628559", "18 Pioneer Crescent, #05-11, Singapore 628559"),
        "contact_name": (["Tan Hui Min", "Ms. Tan Hui Min"], "Ms. Tan Hui Min"), "contact_title": ("Commercial Manager", "Commercial Manager"),
        "phone_day": "+65 6795 3310", "tel": ("+65 6795 3310", "+65 6795 3310"), "email": "huimin.tan@harborline.example",
        "services": ("Ocean and air freight forwarding, customs brokerage for semiconductor equipment",
                     "Ocean and air freight forwarding, customs brokerage for semiconductor equipment"),
        "established": ("2017-08-02", "2 August 2017"), "service_area": ("apac", "Geographic service area: Asia-Pacific"),
        "business_type": ("private_limited", "Business type: Private Limited Company"), "org_type": ("foreign", "Singapore 628559"),
        "insurance": ("insured", "Insurance: Insured"), "licensing": ("licensed", "Licensing: Licensed"),
        "license_number": "SG-CUS-0048821", "gross_sales": ("12400000", "SGD 12,400,000"),
        "bank_name": "Straits Mercantile Bank", "beneficiary": ("Harborline Freight Pte. Ltd.", "Beneficiary name: Harborline Freight Pte. Ltd."),
        "account_name": ("Harborline Freight Pte. Ltd.", "Beneficiary name: Harborline Freight Pte. Ltd."),
        "account_number": "072-118845-3", "account_no": ("072-118845-3", "072-118845-3"), "swift": "SMBKSGSGXXX",
        "payment_terms": ("net45", "Net 45"), "currency": ("SGD", "Currency: SGD"), "foreign": (True, "Singapore 628559"),
        "invoice_type": ("foreign_invoice", "Singapore 628559"),
    },
    "travel-sato-kenji": {
        "emp_no": "J-30875", "name": (["佐藤 健一", "佐藤健一"], "佐藤 健一"), "dept": ("prod_eng", "生産技術部 プロセス開発課"),
        "title": "主任", "cost_center": ("CC-2210", "CC-2210"), "approver": ("u_yamamoto", "山本 由美"),
        "email": "k.sato@kestrel-semi.example", "mobile": "080-4412-7765",
        "dest_country": ("TW", "台湾 新竹市"), "dest_city": (["新竹市", "新竹"], "新竹市"),
        "purpose": ("新竹工場 歩留まり改善会議への出席および工程監査", "新竹工場 歩留まり改善会議への出席および工程監査"),
        "depart_date": ("2026-12-07", "2026年12月7日"), "return_date": ("2026-12-11", "2026年12月11日"),
        "outbound_flight": ("BR 197", "BR 197"), "return_flight": ("BR 198", "BR 198"),
        "hotel": ("新竹サイエンスパーク・レジデンス", "新竹サイエンスパーク・レジデンス"), "visa_needed": ("no", "ビザ：不要"),
        "exp_air_amount": ("98400", "98,400"), "exp_air_cur": ("JPY", "| 航空券（往復） | 98,400 | JPY |"),
        "exp_hotel_amount": ("19200", "19,200"), "exp_hotel_cur": ("TWD", "| 宿泊費 | 19,200 | TWD |"),
        "exp_local_amount": ("3000", "3,000"), "exp_local_cur": ("TWD", "| 現地交通費 | 3,000 | TWD |"),
        "advance_amount": ("60000", "60,000円"), "advance_cur": ("JPY", "60,000円（円建て"),
        "passport_no": "TR8827461", "passport_expiry": ("2031-04-18", "2031-04-18"),
    },
    # ---------------- eval-only personas ----------------
    "eval-maria-santos": {
        "family_name": "SANTOS", "given_name": "MARIA ISABEL", "full_name": (["Maria Isabel Santos", "SANTOS, MARIA ISABEL", "Maria Santos"], "SANTOS, MARIA ISABEL"),
        "sex": ("female", "Sex: Female"), "gender": ("female", "Sex: Female"), "dob": ("1990-10-05", "5 October 1990"),
        "nationality": ("PH", "Nationality: Philippines"), "passport_no": "P4419027B", "passport_expiry": ("2033-02-09", "Expires 9 Feb 2033"),
        "occupation": ("engineer", "Senior Quality Engineer"), "marital": ("single", "Marital status: Single"),
        "arrival_date": ("2026-12-14", "14 December 2026"), "flight_no": ("PR 896", "Flight PR 896"),
        "departure_flight": ("", "leave departure flight blank"), "purpose": ("business", "Purpose of visit: Business"),
        "visa_type": ("resident", "Visa type: Resident Visa"), "visa_no": "V-8821556", "stay_type": ("residence", "Hsinchu Science Park Residence"),
        "stay_address": (["No. 2, Gongye E. 2nd Rd., East Dist., Hsinchu City 300", "Hsinchu Science Park Residence, No. 2, Gongye E. 2nd Rd., East Dist., Hsinchu City 300"],
                         "No. 2, Gongye E. 2nd Rd., East Dist., Hsinchu City 300"),
        "address": (["Hsinchu Science Park Residence, No. 2, Gongye E. 2nd Rd., East Dist., Hsinchu City 300", "No. 2, Gongye E. 2nd Rd., East Dist., Hsinchu City 300"],
                    "No. 2, Gongye E. 2nd Rd., East Dist., Hsinchu City 300"),
        "county": ("新竹市", "Hsinchu City 300"), "district": ("東區", "East Dist., Hsinchu City"),
        "phone": "+886 970 228 415", "email": "maria.santos@kestrel-semi.example",
        "visited": (["PH"], "Countries visited in last 14 days: Philippines only"),
        "account_type": ("savings", "Account type: Savings"), "account_category": ("individual", "Account category: Individual"),
        "education": ("bachelor", "Bachelor's degree"), "monthly_income": ("142000", "TWD 142,000"),
        "id_form": ("passport", "Form of identification: Passport"), "mother_maiden": "Reyes",
        "residency": ("foreign_national", "Nationality: Philippines"), "declare": (True, "Case GM-2026-0193"),
    },
    "eval-bluecrest": {
        "first_name": "Jordan", "middle_initial": ("A", "middle initial A"), "last_name": "Pierce", "suffix": ("", "no suffix"),
        "preferred_name": ("Jordan", 'goes by "Jordan"'), "position": ("Controller", "Controller"),
        "email": "jpierce@bluecrest-analytics.example", "email_confirm": ("jpierce@bluecrest-analytics.example", "jpierce@bluecrest-analytics.example"),
        "country_code": ("1", "+1"), "day_phone": ("(302) 555-0148", "(302) 555-0148"), "mobile_country_code": ("1", "+1"),
        "mobile_phone": ("(302) 555-0193", "(302) 555-0193"), "user_id": ("bluecrest.jpierce", "bluecrest.jpierce"),
        "esign": ("Jordan A. Pierce", "electronic signature: Jordan A. Pierce"), "accept_terms": (True, "Jordan approved accepting the Delaware portal usage terms"),
        "certify": (True, "attests the information is accurate"),
        "street1": ("1201 N Orange St", "1201 N Orange St"), "street2": ("Suite 700", "Suite 700"), "city": ("Wilmington", "Wilmington, DE 19801"),
        "state": ("DE", "Wilmington, DE 19801"), "zip": ("19801", "DE 19801"), "urbanization": ("", "Wilmington, DE 19801"),
        "org_name": "Bluecrest Analytics LLC", "legal_name": ("Bluecrest Analytics LLC", "Bluecrest Analytics LLC"), "fein": "87-4419025",
        "tax_id": ("87-4419025", "FEIN: 87-4419025"),
        "business_type": ("llc", "Limited Liability Company"), "established": ("2019-03-11", "11 March 2019"),
        "company_address": (["1201 N Orange St, Suite 700, Wilmington, DE 19801"], "1201 N Orange St, Suite 700, Wilmington, DE 19801"),
        "contact_name": (["Jordan A. Pierce", "Jordan Pierce"], "Jordan A. Pierce"), "contact_title": ("Controller", "Controller"),
        "phone_day": ("(302) 555-0148", "(302) 555-0148"), "phone_evening": ("", "Evening phone: none"),
        "services": ("Data analytics and forecasting consulting", "Data analytics and forecasting consulting"),
        "service_area": ("north_america", "Geographic service area: North America"), "gross_sales": ("3200000", "USD 3,200,000"),
        "insurance": ("insured", "Insurance: Insured"), "licensing": ("not_licensed", "Licensing: Not licensed"),
        "bank_name": "First Brandywine Trust", "beneficiary": ("Bluecrest Analytics LLC", "Beneficiary: Bluecrest Analytics LLC"),
        "account_number": "4400918273",
    },
    "eval-ahmed-rahman": {
        "first_name": "Ahmed", "last_name": "Rahman", "middle_name": ("", "no middle name"), "sex": ("male", "Sex: Male"),
        "dob": ("1979-01-26", "26/01/1979"), "marital": ("married", "Married"), "nationality": ("BD", "Nationality: Bangladesh"),
        "language": ("english", "Preferred language: English"),
        "street": (["9F, No. 150, Sec. 2, Xinyi Rd., Da'an Dist."], "9F, No. 150, Sec. 2, Xinyi Rd., Da'an Dist."),
        "city": ("Taipei City", "Taipei City 106"), "postal": ("106", "Taipei City 106"), "country": ("TW", "Taipei City 106, Taiwan"),
        "phone_cell": "0975-330-418", "phone_home": ("", "Home phone: none"), "email": "ahmed.rahman@inbox.example",
        "occupation": "Data Platform Lead", "employer": "Kestrel Semiconductor Taiwan Ltd.",
        "ec_name": "Nadia Rahman", "ec_phone": "0975-330-427", "ec_relationship": ("spouse", "Nadia Rahman (spouse)"),
        "ins_provider": ("hsh", "Harbor Shield Health"), "policy_number": "HSH-55-901723", "subscriber_rel": ("self", "Subscriber: Self"),
        "ins_effective": ("2025-07-01", "Effective 2025-07-01"),
    },
    "eval-priya-raman": {
        "first_name": "Priya", "middle_name": ("", "Priya / — / Raman"), "last_name": "Raman", "employee_id": "KST-20533",
        "dob": "1995-06-02", "gender": ("female", "Female"), "marital": ("married", "Married"), "nationality": ("IN", "India"),
        "job_title": ("data_platform_eng", "Data Platform Engineer"), "department": ("data_platform", "Data Platform"),
        "work_location": ("neihu", "Taipei HQ — Neihu"), "emp_status": ("ft_contract", "Full-Time Contract"),
        "supervisor": ("u_rahman_a", "Ahmed Rahman (Data Platform Lead)"), "joined_date": ("2026-12-14", "Start date | 2026-12-14"),
        "create_login": (True, "Username to create"), "username": ("priya.raman", "priya.raman (account enabled)"),
        "login_status": ("enabled", "account enabled"), "email": "priya.raman@kestrel-semi.example",
        "requested_for": ("u_raman_p", "Requested for: Priya Raman"), "opened_for_by": ("u_rahman_a", "Opened on behalf by her manager Ahmed Rahman"),
        "request_type": ("app_access", "Request type: Access to application"), "application": ("dwh", "Data Warehouse"),
        "app_role": ("analyst", "Analyst role"), "access_level": ("rw", "Access level: Read/Write"),
        "justification": ("New Data Platform Engineer; maintains ETL pipelines.", "New Data Platform Engineer; maintains ETL pipelines."),
        "needed_by": ("2026-12-14", "Needed by: 2026-12-14"),
    },
}
PERSONAS.update({g["id"]: g["facts"] for g in GENERATED})
EVAL_PERSONAS = sorted(p for p in PERSONAS if p.startswith("eval-"))

# ----------------------------------------------------------------------------------------------
# Option lists (public reference data or fictional)
# ----------------------------------------------------------------------------------------------
COUNTRIES = [("TW", "Taiwan"), ("JP", "Japan"), ("SG", "Singapore"), ("US", "United States"), ("PH", "Philippines"),
             ("GB", "United Kingdom"), ("IN", "India"), ("BD", "Bangladesh"), ("MY", "Malaysia"), ("VN", "Vietnam"),
             ("KR", "Korea, Republic of"), ("HK", "Hong Kong"), ("TH", "Thailand"), ("ID", "Indonesia"), ("DE", "Germany"),
             ("AU", "Australia"), ("CA", "Canada"), ("NG", "Nigeria"), ("PK", "Pakistan"), ("NL", "Netherlands")]
NATIONALITIES = [("TW", "Taiwanese"), ("JP", "Japanese"), ("SG", "Singaporean"), ("US", "American"), ("PH", "Filipino"),
                 ("GB", "British"), ("IN", "Indian"), ("BD", "Bangladeshi"), ("MY", "Malaysian"), ("VN", "Vietnamese"),
                 ("KR", "Korean"), ("TH", "Thai"), ("ID", "Indonesian"), ("DE", "German"), ("NG", "Nigerian"), ("PK", "Pakistani")]
US_STATES = [("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"), ("CA", "California"), ("CO", "Colorado"),
             ("CT", "Connecticut"), ("DE", "Delaware"), ("DC", "District of Columbia"), ("FL", "Florida"), ("GA", "Georgia"),
             ("HI", "Hawaii"), ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"), ("KS", "Kansas"),
             ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"), ("MA", "Massachusetts"),
             ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"), ("MO", "Missouri"), ("MT", "Montana"),
             ("NE", "Nebraska"), ("NV", "Nevada"), ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"),
             ("NY", "New York"), ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"), ("OK", "Oklahoma"),
             ("OR", "Oregon"), ("PA", "Pennsylvania"), ("PR", "Puerto Rico"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
             ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"), ("VT", "Vermont"), ("VA", "Virginia"),
             ("WA", "Washington"), ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming")]
TW_DIST = {
    "臺北市": ["中正區", "大同區", "中山區", "松山區", "大安區", "萬華區", "信義區", "士林區", "北投區", "內湖區", "南港區", "文山區"],
    "新北市": ["板橋區", "三重區", "中和區", "永和區", "新莊區", "新店區", "汐止區", "淡水區"],
    "桃園市": ["桃園區", "中壢區", "龜山區", "蘆竹區", "大園區"],
    "新竹市": ["東區", "北區", "香山區"],
    "新竹縣": ["竹北市", "竹東鎮", "湖口鄉", "新豐鄉", "寶山鄉"],
    "臺中市": ["西屯區", "南屯區", "北屯區", "西區", "大里區"],
    "臺南市": ["東區", "安平區", "永康區", "善化區"],
    "高雄市": ["前鎮區", "苓雅區", "左營區", "鳳山區", "楠梓區"],
}
TW_BANKS = [("004", "004 臺灣銀行"), ("005", "005 臺灣土地銀行"), ("006", "006 合作金庫商業銀行"), ("007", "007 第一商業銀行"),
            ("008", "008 華南商業銀行"), ("009", "009 彰化商業銀行"), ("012", "012 台北富邦商業銀行"), ("013", "013 國泰世華商業銀行"),
            ("017", "017 兆豐國際商業銀行"), ("808", "808 玉山商業銀行"), ("812", "812 台新國際商業銀行"), ("822", "822 中國信託商業銀行")]
USERS = [("u_huang_yt", "Yi-Ting Huang", "yiting.huang@ · Fab Engineering"), ("u_hung_yc", "Yi-Chen Hung", "yichen.hung@ · Process Integration"),
         ("u_huang_yc", "Yi-Chun Huang", "yichun.huang@ · Finance"), ("u_okafor_d", "Daniel Okafor", "daniel.okafor@ · Information Security"),
         ("u_ocampo_d", "Daniel Ocampo", "daniel.ocampo@ · Facilities"), ("u_lin_ps", "Pei-Shan Lin", "peishan.lin@ · Information Security"),
         ("u_chen_wl", "Wei-Lun Chen", "weilun.chen@ · Fab Engineering"), ("u_chang_i", "Ivy Chang", "ivy.chang@ · HR Operations"),
         ("u_raman_p", "Priya Raman", "priya.raman@ · Data Platform"), ("u_ramesh_p", "Priya Ramesh", "priya.ramesh@ · Finance"),
         ("u_rahman_a", "Ahmed Rahman", "ahmed.rahman@ · Data Platform"), ("u_rahmani_a", "Ahmad Rahmani", "ahmad.rahmani@ · Legal"),
         ("u_tseng_a", "Alvin Tseng", "alvin.tseng@ · Global Mobility"), ("u_koh_b", "Benjamin Koh", "benjamin.koh@ · Logistics")]
JP_USERS = [("u_yamamoto", "山本 由美", "生産技術部 部長"), ("u_yamamoto_t", "山本 拓也", "総務部 課長"), ("u_yamada", "山田 由美子", "経理部"),
            ("u_suzuki", "鈴木 真一", "生産技術部"), ("u_sato_k", "佐藤 健一", "生産技術部 プロセス開発課"), ("u_sato_m", "佐藤 美咲", "品質保証部")]
USERS = {s: USERS + RUN.users[s] for s in ("train", "eval")}          # directory lookups: per-split option lists
JP_USERS = {"train": JP_USERS + RUN.jp_users["train"], "eval": JP_USERS}


# ----------------------------------------------------------------------------------------------
# Field library helpers
# ----------------------------------------------------------------------------------------------
KIND_NORM = {"text": "text", "email": "email", "tel": "phone", "number": "amount", "password": "exact", "date": "date",
             "textarea": "fuzzy", "select": "choice", "cascade": "choice", "radio": "choice", "ariaradio": "choice",
             "dropdown": "choice", "combobox": "choice", "checkbox": "bool", "switch": "bool", "checks": "set",
             "datepicker": "date", "rocdate": "date", "editable": "fuzzy"}


def F(label, kind="text", opts=None, fact=None, norm=None, validate=None, **kw):
    return dict(label=label, kind=kind, opts=opts, fact=fact, norm=norm, validate=validate, **kw)


COMMON = {"hp_website": F("Website", req=False, honeypot=True, note="honeypot: must stay empty")}


def G(title, keys, container=None, show_if=None, panels=None, note=None):
    return dict(title=title, keys=keys, container=container, show_if=show_if, panels=panels, note=note)


def V(variant, split, persona, title, pages, **kw):
    return dict(variant=variant, split=split, persona=persona, title=title, pages=pages, **kw)


# ----------------------------------------------------------------------------------------------
# Themes: page chrome + CSS. Base widget CSS is shared.
# ----------------------------------------------------------------------------------------------
BASE_CSS = """
*{box-sizing:border-box}body{margin:0}
[hidden]{display:none!important}
.ff-error{color:#b42318;font-size:12px;margin-top:4px}
[aria-invalid=true]{border-color:#d92d20!important;outline:1px solid #d92d20}
.ff-banner{padding:10px 14px;margin:0 0 14px;border-radius:4px;background:#ecfdf3;color:#05603a}.ff-banner.bad{background:#fef3f2;color:#b42318}
.ff-dd{position:relative;display:inline-block;min-width:240px}.ff-dd>button{width:100%;text-align:left;padding:8px 30px 8px 10px;background:#fff;border:1px solid #c4c7cc;border-radius:4px;cursor:pointer;font:inherit;position:relative}
.ff-dd>button:after{content:"";position:absolute;right:12px;top:45%;border:5px solid transparent;border-top-color:#555}
.ff-dd ul,.ff-cb ul{position:absolute;z-index:20;left:0;right:0;top:100%;margin:2px 0 0;padding:4px 0;list-style:none;background:#fff;border:1px solid #c4c7cc;border-radius:4px;box-shadow:0 6px 18px rgba(0,0,0,.14);max-height:180px;overflow:auto}
.ff-dd li,.ff-cb li{padding:7px 12px;cursor:pointer}.ff-dd li:hover,.ff-cb li:hover,.ff-dd li[aria-selected=true]{background:#eef2ff}
.ff-cb li small{display:block;color:#667085;font-size:11px}.ff-cb li.ff-empty{color:#667085;cursor:default}
.ff-cb{position:relative;display:inline-block;min-width:260px}.ff-cb input{width:100%}
.ff-dp{position:relative;display:inline-flex;gap:4px;align-items:center}.ff-cal-btn{padding:6px 9px;cursor:pointer}
.ff-cal{position:absolute;z-index:30;top:100%;left:0;background:#fff;border:1px solid #c4c7cc;border-radius:6px;padding:8px;box-shadow:0 8px 24px rgba(0,0,0,.18);width:260px}
.ff-cal-head{display:flex;gap:4px;margin-bottom:6px}.ff-cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}
.ff-cal-grid button{padding:5px 0;border:0;background:#f2f4f7;border-radius:3px;cursor:pointer;font-size:12px}.ff-cal-grid button:hover{background:#d1e0ff}
[role=switch]{width:44px;height:24px;border-radius:12px;border:0;background:#c4c7cc;position:relative;cursor:pointer;vertical-align:middle}
[role=switch] .knob{position:absolute;top:3px;left:3px;width:18px;height:18px;border-radius:50%;background:#fff;transition:left .15s}
[role=switch][aria-checked=true]{background:var(--accent,#2563eb)}[role=switch][aria-checked=true] .knob{left:23px}
[role=radiogroup].chips{display:flex;flex-wrap:wrap;gap:6px}[role=radiogroup].chips [role=radio]{padding:6px 12px;border:1px solid #c4c7cc;border-radius:16px;cursor:pointer;background:#fff}
[role=radiogroup].chips [role=radio][aria-checked=true]{background:var(--accent,#2563eb);color:#fff;border-color:transparent}
.ff-opts input,.chk input{width:auto!important;min-width:0!important}.ff-opts label{display:block;margin:4px 0}.ff-opts.inline label{display:inline-block;margin-right:16px}
.ff-roc select{margin:0 4px;min-width:0!important;width:auto!important}
[contenteditable]{min-height:70px;border:1px solid #c4c7cc;border-radius:4px;padding:8px;background:#fff}
.ff-hp{position:absolute;left:-10000px;top:auto;width:1px;height:1px;overflow:hidden}
.ff-progress{display:flex;gap:6px;list-style:none;padding:0;margin:0 0 16px;counter-reset:s}
.ff-progress li{flex:1;padding:8px;border-bottom:3px solid #d0d5dd;color:#667085;font-size:13px}.ff-progress li.current{border-color:var(--accent,#2563eb);color:#101828;font-weight:600}
.ff-nav{display:flex;gap:10px;margin-top:18px}.ff-done{padding:40px;text-align:center}
.ff-loading{padding:60px;text-align:center;color:#667085}
.ff-tabs [role=tablist]{display:flex;border-bottom:1px solid #d0d5dd;margin-bottom:12px}
.ff-tabs [role=tab]{padding:8px 16px;border:0;background:none;cursor:pointer;border-bottom:2px solid transparent;font:inherit}
.ff-tabs [role=tab].active{border-bottom-color:var(--accent,#2563eb);font-weight:600}
.ff-sticky{position:sticky;top:0;z-index:15;display:flex;justify-content:flex-end;align-items:center;gap:12px;padding:8px 10px;margin-bottom:12px;background:rgba(255,255,255,.97);border:1px solid #d0d5dd;border-radius:4px}
.ff-terms{height:180px;overflow:auto;border:1px solid #c4c7cc;padding:10px 14px;background:#fafafa;font-size:13px;line-height:1.5}
"""

THEMES = {
    "servicenow": dict(lang="en", label_mode="left", css="""
body{font:13px/1.4 "Source Sans Pro",Arial,sans-serif;background:#f6f7f7;color:#1d2a35;--accent:#278efc}
header.top{background:#293e40;color:#fff;padding:8px 16px;display:flex;gap:18px;align-items:center}header.top b{font-size:15px}header.top a{color:#cfe3e4;text-decoration:none}
.layout{display:flex}nav.side{width:210px;background:#303a46;min-height:100vh;padding:10px 0}nav.side a{display:block;color:#d3d8dd;padding:6px 16px;text-decoration:none;font-size:12px}
main{flex:1;padding:14px 22px}.ff-titlebar{background:#e6e9eb;padding:8px 12px;border:1px solid #cbd1d6;display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.ff-group{background:#fff;border:1px solid #cbd1d6;padding:12px 16px;margin-bottom:12px}.ff-group h3{margin:0 0 10px;font-size:14px}
.row{display:grid;grid-template-columns:200px 1fr;gap:8px;align-items:start;margin:8px 0}.row>label,.row>.lbl{text-align:right;padding-top:6px}
.req{color:#c8102e;margin-right:3px}input,select,textarea{font:inherit;padding:6px 8px;border:1px solid #b5bdc4;border-radius:3px;min-width:260px;background:#fff}textarea{width:100%;min-height:70px}
button.btn{background:#fff;border:1px solid #8a959e;padding:6px 14px;border-radius:3px;cursor:pointer}button.primary{background:#278efc;color:#fff;border-color:#278efc}
""", chrome=lambda t, body: f"""<header class="top"><b>Service Portal</b><a href="#">Home</a><a href="#">Catalog</a><a href="#">Knowledge</a><a href="#">My Requests</a><span style="margin-left:auto">Kestrel IT · Search <input aria-label="Global search" style="min-width:160px"></span></header>
<div class="layout"><nav class="side" aria-label="Application navigator"><a href="#">Self-Service</a><a href="#">Incidents</a><a href="#">Requested Items</a><a href="#">Hardware Catalog</a><a href="#">Software Catalog</a><a href="#">Approvals</a><a href="#">Assets</a></nav>
<main><div class="ff-titlebar"><strong>{E(t)}</strong><span><button class="btn" type="button">Save draft</button> <button class="btn" type="button">Cancel</button></span></div>{body}</main></div>"""),
    "openemr": dict(lang="en", label_mode="for", css="""
body{font:14px/1.45 -apple-system,"Segoe UI",Roboto,Arial,sans-serif;background:#fff;color:#212529;--accent:#0d6efd}
.navbar{background:#343a40;color:#fff;padding:8px 16px;display:flex;gap:16px}.navbar a{color:#adb5bd;text-decoration:none}
.container{max-width:1050px;margin:16px auto;padding:0 16px}.ff-group{border:1px solid #dee2e6;border-radius:4px;margin-bottom:14px}
.ff-group h3{margin:0;padding:8px 12px;background:#f8f9fa;border-bottom:1px solid #dee2e6;font-size:15px}.ff-group .body{padding:12px;display:grid;grid-template-columns:repeat(3,1fr);gap:10px 16px}
.row label{display:block;font-weight:600;font-size:13px;margin-bottom:3px}.req{color:#dc3545}
input,select,textarea{width:100%;font:inherit;padding:6px 10px;border:1px solid #ced4da;border-radius:4px;background:#fff}.ff-dd,.ff-cb{min-width:0;width:100%}
.btn{padding:6px 14px;border-radius:4px;border:1px solid #6c757d;background:#fff;cursor:pointer}.primary{background:#0d6efd;color:#fff;border-color:#0d6efd}
""", chrome=lambda t, body: f"""<div class="navbar"><b>OpenEMR</b><a href="#">Calendar</a><a href="#">Finder</a><a href="#">Flow</a><a href="#">Recalls</a><a href="#">Messages</a><a href="#">Patient</a><a href="#">Fees</a><a href="#">Reports</a><span style="margin-left:auto">front-desk · Neihu Riverside Clinic</span></div>
<div class="container"><h2>{E(t)}</h2>{body}</div>"""),
    "parabank": dict(lang="en", label_mode="table", css="""
body{font:12px Verdana,Arial,sans-serif;background:#fff;color:#000;--accent:#4c7b8e}#headerPanel{background:#00546e;height:76px;color:#fff;padding:14px 22px;font:bold 26px Georgia,serif}
#headerPanel small{display:block;font:12px Verdana;color:#cde}#bodyPanel{display:flex;max-width:980px;margin:0 auto}#leftPanel{width:200px;background:#d4e6ec;padding:14px}
#leftPanel a{display:block;color:#00546e;margin:6px 0}#rightPanel{flex:1;padding:16px 22px}h1.title{color:#00546e;font:bold 18px Georgia,serif}
table.form{border-collapse:collapse}table.form td{padding:5px 6px}td.lbl{text-align:right;max-width:330px}input,select{font:inherit;padding:3px;border:1px solid #888;width:200px}
.button{background:#4c7b8e;color:#fff;border:0;padding:5px 16px;cursor:pointer;border-radius:3px}.ff-group h3{color:#00546e;font-size:14px}.req{color:#c00}
""", chrome=lambda t, body: f"""<div id="headerPanel">ParaBank<small>Experience the difference</small></div>
<div id="bodyPanel"><div id="leftPanel"><b>Account Services</b><a href="#">Open New Account</a><a href="#">Accounts Overview</a><a href="#">Transfer Funds</a><a href="#">Bill Pay</a><a href="#">Find Transactions</a><a href="#">Update Contact Info</a><a href="#">Request Loan</a><a href="#">Log Out</a></div>
<div id="rightPanel"><h1 class="title">{E(t)}</h1>{body}</div></div><p style="text-align:center;color:#666">© Parasoft-style demo bank (rebuilt for training). All rights reserved.</p>"""),
    "orangehrm": dict(lang="en", label_mode="for", css="""
body{font:14px/1.4 "Nunito Sans",Arial,sans-serif;background:#f6f6f6;color:#64728c;--accent:#ff7b1d}
aside{position:fixed;left:0;top:0;bottom:0;width:230px;background:#fff;box-shadow:2px 0 8px rgba(0,0,0,.05);padding:18px}aside b{color:#ff7b1d;font-size:20px}aside a{display:block;padding:9px 12px;margin:3px 0;border-radius:20px;color:#64728c;text-decoration:none}aside a.on{background:#ff7b1d;color:#fff}
.topbar{margin-left:230px;background:#fff;padding:14px 24px;color:#1e2b45;font-size:20px;font-weight:700;border-bottom-left-radius:30px}.content{margin-left:230px;padding:22px}
.card{background:#fff;border-radius:12px;padding:22px 26px}.card h2{margin:0 0 16px;color:#1e2b45;font-size:16px}.ff-group{border-top:1px solid #e8eaef;padding-top:14px;margin-top:14px}.ff-group h3{font-size:14px;color:#1e2b45}
.ff-group .body{display:grid;grid-template-columns:repeat(3,1fr);gap:14px 22px}.row label{display:block;font-size:12px;margin-bottom:4px}
input,select,textarea{width:100%;font:inherit;padding:9px 12px;border:1px solid #e8eaef;border-radius:8px;background:#fff;color:#1e2b45}.ff-dd,.ff-cb{width:100%;min-width:0}.ff-dd>button{border:1px solid #e8eaef;border-radius:8px;padding:9px 12px}
.req{color:#eb0910}.btn{border-radius:20px;padding:8px 26px;border:1px solid #ff7b1d;color:#ff7b1d;background:#fff;cursor:pointer}.primary{background:#ff7b1d;color:#fff}
""", chrome=lambda t, body: f"""<aside><b>OrangeHRM-style</b><a href="#">Admin</a><a href="#" class="on">PIM</a><a href="#">Leave</a><a href="#">Time</a><a href="#">Recruitment</a><a href="#">My Info</a><a href="#">Performance</a><a href="#">Directory</a></aside>
<div class="topbar">{E(t)}</div><div class="content"><div class="card"><h2>{E(t)}</h2>{body}</div></div>"""),
    "jotform": dict(lang="en", label_mode="for", css="""
body{font:15px/1.5 Inter,"Helvetica Neue",Arial,sans-serif;background:#ecedf3;color:#2c3345;--accent:#0a1551}
.jf{max-width:760px;margin:34px auto;background:#fff;border-radius:6px;box-shadow:0 4px 4px rgba(87,100,126,.21);padding:36px 44px}.jf h1{font-size:28px;margin:0 0 6px}.jf .sub{color:#6f76a7;margin-bottom:24px}
.ff-group h3{font-size:18px;border-bottom:1px solid #eaebf2;padding-bottom:6px}.row{margin:16px 0}.row>label,.row>.lbl,legend{display:block;font-weight:600;margin-bottom:6px}
input,select,textarea{width:100%;font:inherit;padding:10px 12px;border:1px solid #b8bdc9;border-radius:4px;background:#fff}textarea{min-height:90px}.ff-opts input{width:auto}
.req{color:#f23a3c;margin-left:3px}.btn{background:#fff;border:1px solid #b8bdc9;border-radius:4px;padding:10px 26px;cursor:pointer}.primary{background:#18bd5b;border-color:#18bd5b;color:#fff;font-weight:600}
fieldset{border:0;padding:0;margin:16px 0}.ff-dd,.ff-cb{width:100%}
""", chrome=lambda t, body: f"""<div class="jf"><h1>{E(t)}</h1><div class="sub">Please complete all required fields. Information is handled under the bank's privacy notice.</div>{body}</div>
<p style="text-align:center;color:#8d8fa8;font-size:12px">Form layout rebuilt for training · no data leaves this page</p>"""),
    "erp_tw": dict(lang="zh-Hant", label_mode="table", css="""
body{font:14px/1.5 "Noto Sans TC","Microsoft JhengHei",sans-serif;background:#eef1f5;color:#1f2937;--accent:#1d4ed8}
.bar{background:#1e3a5f;color:#fff;padding:10px 18px;display:flex;gap:20px}.bar a{color:#c7d6ea;text-decoration:none}.crumb{padding:8px 18px;color:#475569;font-size:13px}
.panel{max-width:1000px;margin:0 auto 30px;background:#fff;border:1px solid #cbd5e1;border-radius:4px}.panel h1{margin:0;padding:12px 18px;font-size:18px;border-bottom:1px solid #e2e8f0;background:#f8fafc}
.panel .inner{padding:16px 20px}.ff-group h3{font-size:15px;color:#1e3a5f;border-left:4px solid #1d4ed8;padding-left:8px}
table.form{width:100%;border-collapse:collapse}table.form td{border:1px solid #e2e8f0;padding:7px 10px;vertical-align:top}td.lbl{background:#f1f5f9;width:190px;font-weight:500}
input,select,textarea{font:inherit;padding:6px 8px;border:1px solid #94a3b8;border-radius:3px;min-width:260px;background:#fff}textarea{width:100%}
.req{color:#dc2626;font-size:12px;margin-left:4px}.btn{padding:7px 18px;border:1px solid #64748b;background:#fff;border-radius:3px;cursor:pointer}.primary{background:#1d4ed8;color:#fff;border-color:#1d4ed8}
""", chrome=lambda t, body: f"""<div class="bar"><b>鷹揚 ERP</b><a href="#">首頁</a><a href="#">採購管理</a><a href="#">應付帳款</a><a href="#">庫存</a><a href="#">報表</a><span style="margin-left:auto">採購部 王美玲 ｜ 登出</span></div>
<div class="crumb">採購管理 › 供應商管理 › 新增供應商</div><div class="panel"><h1>{E(t)}</h1><div class="inner">{body}</div></div>"""),
    "jp_corp": dict(lang="ja", label_mode="table", css="""
body{font:14px/1.6 "Hiragino Sans","Noto Sans JP",Meiryo,sans-serif;background:#f4f5f7;color:#222;--accent:#0b6e4f}
.hd{background:#fff;border-bottom:3px solid #0b6e4f;padding:10px 20px;display:flex;gap:20px;align-items:center}.hd b{color:#0b6e4f}.hd a{color:#333;text-decoration:none;font-size:13px}
.wrap{max-width:960px;margin:20px auto;background:#fff;padding:20px 28px;border:1px solid #d8dbe0}.wrap h1{font-size:20px;border-bottom:1px solid #ccc;padding-bottom:8px}
.ff-group h3{font-size:15px;background:#eef6f2;padding:6px 10px;border-left:4px solid #0b6e4f}table.form{width:100%;border-collapse:collapse}table.form td{border:1px solid #d8dbe0;padding:8px 10px}
td.lbl{background:#f7f7f9;width:200px}input,select,textarea{font:inherit;padding:5px 8px;border:1px solid #aab;border-radius:2px;min-width:240px;background:#fff}textarea{width:100%}
.req{background:#c0392b;color:#fff;font-size:11px;padding:1px 5px;border-radius:2px;margin-left:6px}.btn{padding:7px 20px;border:1px solid #888;background:#fff;cursor:pointer}.primary{background:#0b6e4f;color:#fff;border-color:#0b6e4f}
""", chrome=lambda t, body: f"""<div class="hd"><b>Kestrel ワークフロー</b><a href="#">申請一覧</a><a href="#">承認待ち</a><a href="#">経費精算</a><a href="#">規程集</a><span style="margin-left:auto;font-size:12px">ログイン中：佐藤 健一</span></div>
<div class="wrap"><h1>{E(t)}</h1><p style="font-size:12px;color:#666">※出張規程第12条に基づき、出発の5営業日前までに申請してください。</p>{body}</div>"""),
    "gforms": dict(lang="en", label_mode="aria", css="""
body{font:14px/1.5 Roboto,Arial,sans-serif;background:#f0ebf8;color:#202124;--accent:#673ab7}.gf{max-width:640px;margin:12px auto}
.gf .head{background:#fff;border-radius:8px;border-top:10px solid #673ab7;padding:22px 24px;margin-bottom:12px}.gf .head h1{margin:0 0 8px;font-size:30px;font-weight:400}
.row,.ff-group>h3{background:#fff;border-radius:8px;padding:22px 24px;margin:0 0 12px;border:1px solid #dadce0}.ff-group>h3{background:#673ab7;color:#fff;font-weight:400;font-size:16px}
.q{font-size:16px;margin-bottom:14px}.req{color:#d93025;margin-left:4px}input[type=text],input[type=email],input:not([type]),textarea,select{width:100%;border:0;border-bottom:1px solid #dadce0;padding:6px 0;font:inherit;background:transparent}
.ff-opts label{display:block;margin:10px 0}.btn{background:#fff;color:#673ab7;border:1px solid #dadce0;border-radius:4px;padding:9px 22px;cursor:pointer}.primary{background:#673ab7;color:#fff;border-color:#673ab7}
""", chrome=lambda t, body: f"""<div class="gf"><div class="head"><h1>{E(t)}</h1><div>Kestrel Academy · internal training registration. <span style="color:#d93025">* Indicates required question</span></div></div>{body}
<p style="text-align:center;color:#666;font-size:12px">This form was created inside Kestrel Semiconductor. Never submit passwords through forms.</p></div>"""),
    "uswds": dict(lang="en", label_mode="for", css="""
body{font:17px/1.5 "Source Sans Pro","Helvetica Neue",Arial,sans-serif;color:#1b1b1b;background:#fff;--accent:#005ea2}
.usa-banner{background:#f0f0f0;font-size:12px;padding:4px 20px}.usa-header{border-bottom:1px solid #dfe1e2;padding:16px 20px;font-weight:700;font-size:22px}
.grid{max-width:640px;margin:24px auto;padding:0 16px}.row{margin-top:24px}.row>label,.row>.lbl,legend{display:block;font-weight:400;margin-bottom:6px}.hint{color:#71767a;font-size:15px}
input,select,textarea{font:inherit;padding:8px;border:1px solid #565c65;border-radius:0;width:100%;max-width:30rem;background:#fff}.req{color:#b50909}
.btn{background:#005ea2;color:#fff;border:0;border-radius:4px;padding:12px 22px;font-weight:700;cursor:pointer}.btn.outline{background:#fff;color:#005ea2;box-shadow:inset 0 0 0 2px #005ea2}.primary{}
fieldset{border:0;padding:0}.ff-group h3{font-size:22px;margin-top:30px}
""", chrome=lambda t, body: f"""<div class="usa-banner">An official-style website template (rebuilt for training; not a government site)</div><div class="usa-header">State Revenue Portal</div>
<div class="grid"><h1>{E(t)}</h1><p class="hint">Required fields are marked with an asterisk (<span class="req">*</span>).</p>{body}</div>"""),
    "delaware": dict(lang="en", label_mode="left", css="""
body{font:14px/1.45 "Helvetica Neue",Arial,sans-serif;background:#f3f3f3;color:#333;--accent:#1f4e79}.dh{background:#1f4e79;color:#fff;padding:12px 24px;font-size:20px}.dh small{display:block;font-size:12px;color:#c9d7e6}
.dn{background:#fff;border-bottom:1px solid #ddd;padding:8px 24px}.dn a{margin-right:16px;color:#1f4e79}.dc{max-width:900px;margin:18px auto;background:#fff;padding:20px 28px;border:1px solid #ddd}
.row{display:grid;grid-template-columns:240px 1fr;gap:10px;margin:10px 0;align-items:center}.row>label,.row>.lbl{text-align:right;font-weight:600}.req:before{content:"* ";color:#c00}.req{color:#c00}
input,select{font:inherit;padding:6px 8px;border:1px solid #aaa;border-radius:3px;width:320px;background:#fff}.btn{padding:7px 18px;border:1px solid #1f4e79;background:#fff;color:#1f4e79;cursor:pointer;border-radius:3px}.primary{background:#1f4e79;color:#fff}
""", chrome=lambda t, body: f"""<div class="dh">Revenue Taxpayer Portal<small>Division of Revenue — register for secure services (training replica)</small></div>
<div class="dn"><a href="#">Home</a><a href="#">Individuals</a><a href="#">Businesses</a><a href="#">Global Help</a><a href="#">English</a> | <a href="#">French</a></div>
<div class="dc"><h2>{E(t)}</h2>{body}</div><p style="text-align:center;font-size:12px;color:#777">Live Chat is available Monday through Friday 8 AM–5 PM.</p>"""),
    "twac": dict(lang="zh-Hant", label_mode="for", css="""
body{font:15px/1.55 "Noto Sans TC",Arial,sans-serif;background:#f5f7fa;color:#1f2933;--accent:#0f766e}.th{background:#0f766e;color:#fff;padding:12px 20px}.th b{font-size:18px}.th small{display:block;opacity:.85}
.tw{max-width:760px;margin:20px auto;background:#fff;border-radius:10px;padding:22px 28px;box-shadow:0 2px 10px rgba(0,0,0,.06)}.row{margin:14px 0}.row>label,.row>.lbl,legend{display:block;font-weight:600;margin-bottom:5px}
input,select,textarea{width:100%;font:inherit;padding:9px 11px;border:1px solid #cbd2d9;border-radius:6px;background:#fff}.ff-opts input{width:auto}.req{color:#c81e1e;margin-left:4px}.ff-group h3{color:#0f766e}
.btn{padding:9px 22px;border-radius:6px;border:1px solid #0f766e;color:#0f766e;background:#fff;cursor:pointer}.primary{background:#0f766e;color:#fff}fieldset{border:0;padding:0}.ff-dd,.ff-cb{width:100%}
""", chrome=lambda t, body: f"""<div class="th"><b>入境登記表 Arrival Card</b><small>線上填寫 Online submission · 訓練用重建頁面 (not the live system)</small></div><div class="tw"><h2>{E(t)}</h2>{body}</div>"""),
}

MESSAGES = {
    "en": dict(required="This field is required.", email="Enter a valid email address.", ubn="Invalid business ID.", date="Enter a valid date.",
               format="Invalid format.", match="Values do not match.", fix="Please correct the highlighted fields.", noMatch="No matches found",
               searching="Searching…", doneTitle="Submitted", doneBody="Your submission has been received.", next="Next", back="Back",
               submit="Submit", select="-- Select --", none="-- None --", reqmark="*", loading="Loading form…", cal="Choose date", draft="Save draft"),
    "zh-Hant": dict(required="此欄位為必填。", email="電子郵件格式不正確。", ubn="統一編號檢查碼錯誤。", date="日期格式不正確。", format="格式不正確。",
                    match="兩次輸入不一致。", fix="請修正標示的欄位。", noMatch="查無資料", searching="查詢中…", doneTitle="已送出",
                    doneBody="資料已送出，等待主管簽核。", next="下一步", back="上一步", submit="送出", select="請選擇", none="無",
                    reqmark="必填", loading="表單載入中…", cal="選擇日期", draft="暫存"),
    "ja": dict(required="必須項目です。", email="メールアドレスの形式が正しくありません。", ubn="番号が正しくありません。", date="日付の形式が正しくありません。",
               format="形式が正しくありません。", match="入力内容が一致しません。", fix="エラーの項目を修正してください。", noMatch="該当なし",
               searching="検索中…", doneTitle="申請しました", doneBody="承認者に通知されました。", next="次へ", back="戻る", submit="申請する",
               select="選択してください", none="なし", reqmark="必須", loading="読み込み中…", cal="日付を選択", draft="一時保存"),
}


# ----------------------------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------------------------
class Page:
    def __init__(self, fam, v):
        self.fam, self.v = fam, v
        self.theme = THEMES[v.get("theme", fam["theme"])]
        self.lang = v.get("lang", self.theme["lang"])
        self.msg = MESSAGES["en" if self.lang.startswith("en") else self.lang]
        self.mode = v.get("label_mode", self.theme["label_mode"])
        self.fields = []           # resolved field dicts in page order
        self.rng = random.Random(f"{fam['family']}/{v['variant']}")

    def resolve(self, ref, page_no, show_if):
        key, ov = (ref, {}) if isinstance(ref, str) else ref
        f = {**(self.fam["fields"].get(key) or COMMON[key]), **self.v.get("overrides", {}).get(key, {}), **ov}
        if isinstance(f.get("opts"), dict):          # per-split option list (directories)
            f["opts"] = f["opts"][self.v["split"]]
        f.update(key=key, id=f"{self.v.get('id_prefix', 'f')}_{key}", page=page_no, show_if=show_if)
        f.setdefault("req", True)
        if hasattr(self, "exp"):
            f["expected"], f["accept"], f["infeasible"] = self.exp[key]
        self.fields.append(f)
        return f

    def label_html(self, f):
        star = f'<span class="req" aria-hidden="true">{self.msg["reqmark"]}</span>' if f["req"] and not f.get("hide_req") else ""
        return E(f["label"]) + star

    def attrs(self, f, kind):
        a = f'data-ff-key="{f["key"]}" data-ff-kind="{kind}"' + (' data-ff-required="1"' if f["req"] else "")
        if f.get("validate"):
            a += f' data-ff-validate="{E(f["validate"])}"'
        if f.get("msg"):
            a += f' data-ff-msg="{E(f["msg"])}"'
        return a

    def widget(self, f):
        k, i, m = f["kind"], f["id"], self.msg
        opts = f.get("opts") or []
        ph = E(f.get("placeholder", f["label"] if f.get("ph_only") else ""))
        aria = f' aria-labelledby="{i}-q"' if self.mode == "aria" else ""
        req_attr = ' aria-required="true"' if f["req"] else ""
        if k in ("text", "email", "tel", "number", "password", "date"):
            t = {"number": "text", "tel": "tel"}.get(k, k)
            extra = ' inputmode="decimal"' if k == "number" else ""
            return f'<input id="{i}" name="{f["key"]}" type="{t}" placeholder="{ph}" autocomplete="off"{extra}{aria}{req_attr} {self.attrs(f, "input")}>'
        if k == "textarea":
            return f'<textarea id="{i}" name="{f["key"]}" rows="3" placeholder="{ph}"{aria}{req_attr} {self.attrs(f, "input")}></textarea>'
        if k == "select":
            o = "".join(f'<option value="{E(v)}">{E(lb)}</option>' for v, lb, *_ in opts)
            return f'<select id="{i}" name="{f["key"]}"{aria}{req_attr} {self.attrs(f, "select")}><option value="">{E(f.get("placeholder", m["select"]))}</option>{o}</select>'
        if k == "cascade":
            mp = json.dumps(f["map"], ensure_ascii=False)
            return (f'<select id="{i}" name="{f["key"]}"{aria}{req_attr} {self.attrs(f, "select")} data-ff-parent="{f["parent"]}" '
                    f'data-ff-map="{E(mp)}" data-ff-placeholder="{E(m["select"])}"></select>')
        if k == "radio":
            cls = "ff-opts inline" if f.get("inline") else "ff-opts"
            o = "".join(f'<label><input type="radio" name="{f["key"]}" value="{E(v)}"> {E(lb)}</label>' for v, lb, *_ in opts)
            return f'<div class="{cls}" role="radiogroup" aria-labelledby="{i}-q" {self.attrs(f, "radio")}>{o}</div>'
        if k == "checks":
            o = "".join(f'<label><input type="checkbox" value="{E(v)}"> {E(lb)}</label>' for v, lb, *_ in opts)
            return f'<div class="ff-opts inline" role="group" aria-labelledby="{i}-q" {self.attrs(f, "checks")}>{o}</div>'
        if k == "ariaradio":
            o = "".join(f'<div role="radio" tabindex="0" aria-checked="false" data-value="{E(v)}">{E(lb)}</div>' for v, lb, *_ in opts)
            return f'<div class="chips" role="radiogroup" aria-labelledby="{i}-q" {self.attrs(f, "ariaradio")}>{o}</div>'
        if k == "checkbox":
            return f'<label class="chk"><input type="checkbox" id="{i}" {self.attrs(f, "checkbox")}> {self.label_html(f)}</label>'
        if k == "switch":
            return f'<button type="button" id="{i}" role="switch" aria-checked="false" aria-labelledby="{i}-q" {self.attrs(f, "switch")}><span class="knob"></span></button>'
        if k == "dropdown":
            p = E(f.get("placeholder", m["select"]))
            o = "".join(f'<li role="option" aria-selected="false" data-value="{E(v)}">{E(lb)}</li>' for v, lb, *_ in opts)
            return (f'<div class="ff-dd"><button type="button" id="{i}" aria-haspopup="listbox" aria-expanded="false"{aria} data-ff-placeholder="{p}" '
                    f'{self.attrs(f, "dropdown")}><span class="ff-dd-label">{p}</span></button><ul role="listbox" hidden>{o}</ul></div>')
        if k == "combobox":
            js = json.dumps([list(o) for o in opts], ensure_ascii=False)
            d = f' data-ff-delay="{f["delay"]}"' if f.get("delay") else ""
            mc = f' data-ff-min-chars="{f["min_chars"]}"' if f.get("min_chars") else ""
            return (f'<div class="ff-cb"><input id="{i}" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" autocomplete="off" '
                    f'placeholder="{ph}"{aria}{req_attr} {self.attrs(f, "combobox")} data-ff-options="{E(js)}"{d}{mc}><ul role="listbox" hidden></ul></div>')
        if k == "datepicker":
            fmt = f.get("fmt", "YYYY-MM-DD")
            years = "".join(f'<option>{y}</option>' for y in range(1940, 2041))
            months = "".join(f'<option value="{n}">{n:02d}</option>' for n in range(1, 13))
            typing = ' data-ff-typing="0"' if f.get("no_typing") else ""
            return (f'<div class="ff-dp"><input id="{i}" type="text" placeholder="{E(f.get("placeholder", fmt.lower()))}" autocomplete="off" data-ff-format="{fmt}"{typing}{aria}{req_attr} '
                    f'{self.attrs(f, "datepicker")}><button type="button" class="ff-cal-btn" aria-label="{E(m["cal"])}">&#9638;</button>'
                    f'<div class="ff-cal" role="dialog" aria-label="{E(m["cal"])}" hidden><div class="ff-cal-head"><button type="button" class="ff-cal-prev" aria-label="Previous month">&lsaquo;</button>'
                    f'<select class="ff-cal-m" aria-label="Month">{months}</select><select class="ff-cal-y" aria-label="Year">{years}</select>'
                    f'<button type="button" class="ff-cal-next" aria-label="Next month">&rsaquo;</button></div><div class="ff-cal-grid"></div></div></div>')
        if k == "rocdate":
            ys = "".join(f'<option value="{y}">{y}</option>' for y in range(30, 121))
            ms = "".join(f'<option value="{n}">{n}</option>' for n in range(1, 13))
            ds = "".join(f'<option value="{n}">{n}</option>' for n in range(1, 32))
            return (f'<div class="ff-roc" role="group" aria-labelledby="{i}-q" {self.attrs(f, "rocdate")}>民國<select aria-label="年"><option value=""></option>{ys}</select>年'
                    f'<select aria-label="月"><option value=""></option>{ms}</select>月<select aria-label="日"><option value=""></option>{ds}</select>日</div>')
        if k == "editable":
            return f'<div id="{i}" contenteditable="true" role="textbox" aria-multiline="true" aria-labelledby="{i}-q" {self.attrs(f, "editable")}></div>'
        raise ValueError(k)

    def row(self, f):
        w, i = self.widget(f), f["id"]
        hint = f'<div class="hint">{E(f["hint"])}</div>' if f.get("hint") else ""
        if f["kind"] == "checkbox":
            return f'<tr data-ff-row><td class="lbl"></td><td>{w}{hint}</td></tr>' if self.mode == "table" else f'<div class="row" data-ff-row><span class="lbl"></span><div>{w}{hint}</div></div>'
        if f.get("ph_only"):
            return f'<div class="row" data-ff-row>{w}{hint}</div>'
        grouped = f["kind"] in ("radio", "checks", "ariaradio", "rocdate", "switch", "editable")
        if self.mode == "table":
            return f'<tr data-ff-row><td class="lbl" id="{i}-q">{self.label_html(f)}</td><td>{w}{hint}</td></tr>'
        if self.mode == "aria" or grouped:
            return f'<div class="row" data-ff-row><div class="q lbl" id="{i}-q">{self.label_html(f)}</div><div>{hint}{w}</div></div>'
        return f'<div class="row" data-ff-row><label for="{i}" id="{i}-q">{self.label_html(f)}</label><div>{hint}{w}</div></div>'

    def rows(self, keys, page_no, show_if):
        fs = [self.resolve(r, page_no, show_if) for r in keys]
        inner = "".join(self.row(f) for f in fs)
        return f'<table class="form" role="presentation">{inner}</table>' if self.mode == "table" else f'<div class="body">{inner}</div>'

    def group(self, g, page_no):
        si = f' data-ff-show-if="{g["show_if"]}"' if g.get("show_if") else ""
        title = f"<h3>{E(g['title'])}</h3>" if g.get("title") else ""
        note = f'<p class="hint">{g["note"]}</p>' if g.get("note") else ""
        if g.get("container") == "tabs":
            tabs, panels = [], []
            for n, (pt, keys) in enumerate(g["panels"]):
                pid = f"tab-{page_no}-{n}"
                tabs.append(f'<button type="button" role="tab" aria-controls="{pid}" aria-selected="{str(n == 0).lower()}" class="{"active" if n == 0 else ""}">{E(pt)}</button>')
                panels.append(f'<div role="tabpanel" id="{pid}"{" hidden" if n else ""}>{self.rows(keys, page_no, g.get("show_if"))}</div>')
            return f'<div class="ff-group ff-tabs"{si}>{title}{note}<div role="tablist">{"".join(tabs)}</div>{"".join(panels)}</div>'
        body = self.rows(g["keys"], page_no, g.get("show_if"))
        if g.get("container") in ("shadow", "shadow-open"):
            mode = "open" if g["container"] == "shadow-open" else "closed"
            return f'<div class="ff-group"{si}>{title}{note}<div class="ff-shadow-host" data-ff-shadow="{mode}"><template>{body}</template></div></div>'
        return f'<div class="ff-group"{si}>{title}{note}{body}</div>'

    def build(self):
        v, m = self.v, self.msg
        pages = v["pages"]
        parts = []
        if v.get("intro"):
            parts.append(v["intro"])
        if v.get("sticky_submit"):                    # always-visible submit: pressing it before the optional fields are done is a mistake
            parts.append(f'<div class="ff-sticky"><span>{E(v["title"])}</span><button type="submit" class="btn primary" data-ff-submit>{E(v.get("submit_label", m["submit"]))}</button></div>')
        parts.append('<div class="ff-banner" role="alert" hidden></div>')
        if len(pages) > 1:
            names = v.get("step_names") or [f"Step {n + 1}" for n in range(len(pages))]
            parts.append('<ol class="ff-progress">' + "".join(f"<li>{E(s)}</li>" for s in names) + "</ol>")
        for n, groups in enumerate(pages):
            body = "".join(self.group(g, n) for g in groups)
            if n == len(pages) - 1 and v.get("honeypot"):
                hp = self.resolve("hp_website", n, None)
                body += f'<div class="ff-hp" aria-hidden="true"><label for="{hp["id"]}">Website</label>{self.widget(hp)}</div>'
            back = f'<button type="button" class="btn" data-ff-back>{m["back"]}</button>' if n else ""
            nxt = (f'<button type="submit" class="btn primary" data-ff-submit>{E(v.get("submit_label", m["submit"]))}</button>'
                   if n == len(pages) - 1 else f'<button type="button" class="btn primary" data-ff-next>{m["next"]}</button>')
            draft = f'<button type="button" class="btn">{E(v.get("draft_label", m["draft"]))}</button>'
            nav = f'<div class="ff-nav">{back}{nxt}{draft if v.get("draft") else ""}</div>'
            parts.append(f'<section class="ff-step">{body}{nav}</section>' if len(pages) > 1 else f"{body}{nav}")
        form = f'<form novalidate autocomplete="off">{"".join(parts)}</form>'
        cfg = dict(family=self.fam["family"], variant=v["variant"], keys=[f["key"] for f in self.fields], messages=m,
                   today=TODAY, delay=v.get("delay", 0), refPrefix=v.get("ref", "REQ"),
                   rejectKey=v.get("reject", (None, None))[0], rejectMessage=v.get("reject", (None, None))[1],
                   prefill=self.prefill)
        body = self.theme["chrome"](v["title"], f'<div id="ff-root"><div class="ff-loading">{m["loading"]}</div></div>')
        cfgjs = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
        return f"""<!doctype html>
<html lang="{self.lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(v["title"])}</title>
<style id="ff-style">{BASE_CSS}{self.theme["css"]}</style></head>
<body>{body}
<template id="ff-form">{form}</template>
<script type="application/json" id="ff-config">{cfgjs}</script>
<script>{RUNTIME}</script>
</body></html>
"""

    def wrong(self, right):
        """Up to two wrong prefills for the 'wrong' (recovery) state: one format error, one stale value."""
        out = {}
        by = {f["key"]: f for f in self.fields}
        fmt = [k for k in right if by[k].get("validate") and by[k]["kind"] in ("text", "email", "tel")]
        plain = [k for k in right if k not in fmt and by[k]["kind"] in ("text", "select", "dropdown", "radio", "datepicker", "number", "tel")]
        if fmt:
            k = fmt[0]
            out[k] = right[k].replace("@", " at ") if "@" in right[k] else right[k][:-2] + "x"
        if plain:
            k = self.rng.choice(plain)
            f, val = by[k], right[k]
            if f["kind"] in ("select", "dropdown", "radio"):
                other = [o[0] for o in f["opts"] if o[0] != val]
                out[k] = other[0] if other else val
            elif f["kind"] == "datepicker":
                out[k] = f"{int(val[:4]) - 1}{val[4:]}"
            else:
                out[k] = val[: max(1, len(val) // 2)]
        return out


def expected_for(persona, field):
    fact = field.get("fact") or field["key"]
    if field.get("honeypot"):
        return "", [], "", False
    if fact not in PERSONAS[persona]:
        return None, [], None, True
    raw = PERSONAS[persona][fact]
    val, src = (raw if isinstance(raw, tuple) else (raw, raw))
    alts = []
    if isinstance(val, list) and field["kind"] != "checks":
        val, alts = val[0], val[1:]
    return val, alts, src, False


def collect(fam, v):
    """Resolve every field of a variant (no rendering)."""
    probe = Page(fam, v)
    for n, groups in enumerate(v["pages"]):
        for g in groups:
            for keys in ([g["keys"]] if g.get("container") != "tabs" else [k for _, k in g["panels"]]):
                for r in keys:
                    probe.resolve(r, n, g.get("show_if"))
    if v.get("honeypot"):
        probe.resolve("hp_website", len(v["pages"]) - 1, None)
    return probe


def expected_map(fam, v, probe, pid, ctx_text):
    """{key: (value, accepted_alternates, infeasible)} for one persona; checks source text and option membership."""
    exp = {}
    for f in probe.fields:
        val, alts, src, inf = expected_for(pid, f)
        if isinstance(src, str) and src and src not in ctx_text:
            raise SystemExit(f"{fam['family']}/{v['variant']}: source text for {f['key']!r} not in {pid}: {src!r}")
        if val not in (None, "") and f["kind"] in ("select", "cascade", "dropdown", "radio", "ariaradio", "combobox") and val not in [o[0] for o in f["opts"]]:
            raise SystemExit(f"{fam['family']}/{v['variant']}: {pid}: {f['key']}={val!r} not an option")
        exp[f["key"]] = (val, alts, inf)
    return exp


def persona_entry(probe, exp):
    """What a verifier / recorder needs for one (variant, persona): expected per field, submit flag, prefill values."""
    kind = {f["key"]: f["kind"] for f in probe.fields}

    def shown(f):
        if not f.get("show_if"):
            return True
        k, want = f["show_if"].split("=")
        cur = exp[k][0]
        if cur is None and kind[k] in ("checkbox", "switch"):
            cur = False
        return str(cur).lower() == want
    fields, infeasible, hidden, right = {}, [], [], {}
    for f in probe.fields:
        val, alts, inf = exp[f["key"]]
        empty = False if f["kind"] in ("checkbox", "switch") else ""
        if not shown(f):
            hidden.append(f["key"])
            fields[f["key"]] = empty
        elif inf or f.get("honeypot") or val in (None, ""):
            fields[f["key"]] = empty
            if inf:
                infeasible.append(f["key"])
        else:
            fields[f["key"]] = [val, *alts] if alts else val
            right[f["key"]] = val
    submit = not any(exp[f["key"]][2] and f["req"] and shown(f) for f in probe.fields)
    return dict(submit=submit, fields=fields, infeasible=infeasible, hidden=hidden, prefill=dict(right=right, wrong=probe.wrong(right)))


def meta_for(fam, v, p, entry, pids):
    fields = []
    for f in p.fields:
        fields.append({k: val for k, val in dict(
            label=f["label"], key=f["key"], kind=f["kind"], page=f["page"],
            expected_value_from_context=f["expected"], accept=f["accept"] or None,
            normalization=f.get("norm") or KIND_NORM[f["kind"]], required=f["req"],
            infeasible=f["infeasible"] or None, show_if=f.get("show_if"), honeypot=f.get("honeypot"),
            note=f.get("note")).items() if val is not None})
        # recorder-compat keys (train/docs/episode-format.md): value read from window.__formState().values[key]
        fields[-1].update(id=f["key"], source="state", expected=entry["fields"][f["key"]])
    kinds = {f["kind"] for f in p.fields}
    hard = ["prefilled", "partial", "wrong", "loading"] + (["error"] if v.get("reject") else [])
    extra = dict(scroll=bool(v.get("intro")) or len(p.fields) > 14, infeasible=any(f["infeasible"] for f in p.fields),
                 multi_page=len(v["pages"]) > 1, hidden_tabs=any(g.get("container") == "tabs" for pg in v["pages"] for g in pg),
                 shadow_dom=any((g.get("container") or "").startswith("shadow") for pg in v["pages"] for g in pg),
                 conditional=any(f.get("show_if") for f in p.fields), honeypot=bool(v.get("honeypot")),
                 autocomplete="combobox" in kinds, custom_dropdown="dropdown" in kinds, date_picker="datepicker" in kinds,
                 roc_date="rocdate" in kinds, cascade="cascade" in kinds, delayed_render=bool(v.get("delay")),
                 early_submit_trap=bool(v.get("sticky_submit")), calendar_only=any(f.get("no_typing") for f in p.fields))
    hard += [k for k, on in extra.items() if on]
    blocked = not entry["submit"]
    return dict(
        family=fam["family"], variant=v["variant"], split=v["split"], title=v["title"], language=p.lang,
        source=fam["source"], context=f"contexts/{v['persona']}.md", url=f"forms/{fam['family']}/{v['variant']}/index.html",
        pages=len(v["pages"]), goal=v.get("goal") or fam["goal"],
        contexts=[f"{v['persona']}.md"], entry="index.html", submit=not blocked, locale=p.lang, personas=pids,
        success=dict(require_submitted=not blocked,
                     rule=("all non-infeasible fields match expected (after normalization), infeasible fields empty, "
                           + ("and the form was submitted" if not blocked else "and the form was NOT submitted (a required value is not in the context)"))),
        reject_on_first_submit=dict(key=v["reject"][0], message=v["reject"][1]) if v.get("reject") else None,
        fields=fields, hard_states_supported=hard, notes=v.get("notes", ""),
    )


# ----------------------------------------------------------------------------------------------
# Families (field library + variants). Variants differ in structure, not only wording.
# ----------------------------------------------------------------------------------------------
LOCS = [("neihu", "Taipei HQ — Neihu"), ("hsp_fab3", "Hsinchu Science Park — Fab 3"), ("hsp_fab2", "Hsinchu Science Park — Fab 2"),
        ("tainan", "Tainan Science Park — Assembly"), ("sg", "Singapore Regional Office")]
ASSETS = [("KST-NB-30982", "KST-NB-30982", "Laptop · Okafor, Daniel · ThinkBook-class 14"), ("KST-NB-27410", "KST-NB-27410", "Laptop · retired 2026-08"),
          ("KST-NB-30928", "KST-NB-30928", "Laptop · Ocampo, Daniel"), ("KST-MON-1182", "KST-MON-1182", "Monitor 27\""),
          ("KST-VPN-GW2", "KST-VPN-GW2", "VPN gateway · Neihu DC")]
ASSETS = {s: ASSETS + RUN.assets[s] for s in ("train", "eval")}
GROUPS = [("servicedesk", "Service Desk"), ("netops", "Network Operations"), ("netsec", "Network Security"),
          ("endpoint", "Endpoint Engineering"), ("dba", "Database Administration"), ("iam", "Identity & Access Management")]
APPS = [("dwh", "Data Warehouse", "Snowflake-class analytics warehouse"), ("dwh_stage", "Data Warehouse — Staging", "non-production"),
        ("mes", "MES (Manufacturing Execution)", "fab floor"), ("erp", "ERP Finance", "SAP-class"), ("jira", "Issue Tracker", "engineering"),
        ("bi", "BI Dashboards", "reporting")]
SUBCATS = {"network": [("vpn", "VPN"), ("wifi", "Wireless"), ("dns", "DNS")], "hardware": [("laptop", "Laptop"), ("monitor", "Monitor"), ("printer", "Printer")],
           "software": [("email", "Email"), ("os", "Operating System"), ("office", "Office apps")], "inquiry": [("howto", "How-to")],
           "database": [("db_access", "Access"), ("db_perf", "Performance")]}
IMPACT = [("1", "1 - High"), ("2", "2 - Medium"), ("3", "3 - Low")]

ITSM = dict(family="itsm-request", theme="servicenow", source="ServiceNow-style catalog/incident forms (WorkArena README task types; rebuilt, no login)",
            goal="Using the context, fill in this IT request form for the person described and submit it.", fields={
    "requested_for": F("Requested for", "combobox", USERS, delay=400, placeholder="Search users"),
    "laptop_model": F("Model", "select", [("std14", 'Standard Laptop 14" (16 GB)'), ("eng16", 'Engineering Workstation Laptop 16" (32 GB)'),
                                         ("eng16_64", 'Engineering Workstation Laptop 16" (64 GB, GPU)'), ("design14", 'Design Laptop 14" (high-DPI)')]),
    "location": F("Deliver to", "select", LOCS),
    "needed_by": F("Needed by", "datepicker", fmt="YYYY-MM-DD"),
    "justification": F("Business justification", "textarea"),
    "extra_monitor": F("Also request an external monitor", "checkbox", req=False),
    "cost_center": F("Cost center", validate=r"re:^CC-\d{4}$", msg="Use the format CC-1234", placeholder="CC-0000"),
    "caller": F("Caller", "combobox", USERS, delay=300),
    "inc_category": F("Category", "select", [("inquiry", "Inquiry / Help"), ("software", "Software"), ("hardware", "Hardware"), ("network", "Network"), ("database", "Database")]),
    "inc_subcategory": F("Subcategory", "cascade", [o for v in SUBCATS.values() for o in v], parent="inc_category", map=SUBCATS),
    "ci": F("Configuration item", "combobox", ASSETS, placeholder="Asset tag"),
    "impact": F("Impact", "select", IMPACT), "urgency": F("Urgency", "select", IMPACT),
    "contact_pref": F("Contact type", "dropdown", [("email", "Email"), ("phone", "Phone"), ("self_service", "Self-service"), ("walk_in", "Walk-in"), ("chat", "Chat")]),
    "assign_group": F("Assignment group", "combobox", GROUPS),
    "short_desc": F("Short description"), "inc_desc": F("Description", "textarea"),
    "opened_for_by": F("Opened by", "combobox", USERS),
    "request_type": F("Request type", "dropdown", [("app_access", "Access to application"), ("hardware", "New hardware"), ("software", "Software installation"), ("other", "Other")]),
    "application": F("Application", "combobox", APPS, min_chars=2),
    "app_role": F("Role", "dropdown", [("viewer", "Viewer"), ("analyst", "Analyst"), ("developer", "Developer"), ("admin", "Administrator")]),
    "access_level": F("Access level", "ariaradio", [("ro", "Read only"), ("rw", "Read/Write"), ("admin", "Admin")]),
}, variants=[
    V("hardware-laptop", "train", "emp-huang-yiting", "Request: Laptop (new hire)", [[
        G("Requested item", ["requested_for", "laptop_model", "location", "needed_by", "extra_monitor", "cost_center", "justification"])]],
      reject=("cost_center", "Cost center could not be verified against Finance — please re-enter it."), ref="RITM",
      notes="Reference field resolves after a 400 ms lookup; typed text without picking a suggestion is not committed."),
    V("hardware-tabs", "train", "emp-huang-yiting", "Hardware Catalog — Engineering Laptop", [[
        G("", None, container="tabs", panels=[
            ("Item", [("laptop_model", {"kind": "dropdown", "label": "Hardware item"}), "extra_monitor"]),
            ("Delivery", [("location", {"kind": "dropdown", "label": "Delivery location"}), ("needed_by", {"label": "Required by date", "fmt": "MM/DD/YYYY"})]),
            ("Requester", [("requested_for", {"label": "On behalf of (user)", "min_chars": 3}), ("cost_center", {"label": "Charge to cost center"})]),
            ("Notes", [("justification", {"kind": "editable", "label": "Why is this needed?"})])])]],
      honeypot=True, draft=True, ref="RITM", notes="Fields hidden in inactive tabs; justification is contenteditable; date in MM/DD/YYYY."),
    V("incident-shadow", "train", "emp-okafor-daniel", "Create Incident", [[
        G("Caller", ["caller", "contact_pref"], container="shadow"),
        G("Classification", ["inc_category", "inc_subcategory", "ci", "impact", "urgency", "assign_group"]),
        G("Details", ["short_desc", "inc_desc"])]],
      delay=800, ref="INC", notes="Caller block lives in a closed shadow root; subcategory depends on category; page renders after 800 ms."),
    V("access-request-wizard", "eval", "eval-priya-raman", "Request Access to an Application", [
        [G("Who is this for?", [("requested_for", {"label": "Employee"}), "opened_for_by", "request_type"])],
        [G("Access", ["application", "app_role", "access_level", ("needed_by", {"fmt": "DD/MM/YYYY", "label": "Access needed by"})])],
        [G("Justification", ["justification"])]],
      step_names=["Requester", "Access", "Justification"], ref="RITM", notes="Eval: 3-step wizard, two similar user lookups (Priya Raman vs Priya Ramesh)."),

    V("incident-quick-sticky", "train", "emp-okafor-daniel", "New Incident — Quick Form", [[
        G("What is happening?", ["short_desc", ("inc_desc", {"kind": "editable"})]),
        G("Who and what", [("caller", {"label": "Affected user", "min_chars": 3}), ("ci", {"label": "Affected device (asset tag)", "delay": 500}),
                           ("contact_pref", {"kind": "radio", "inline": True, "label": "Preferred contact"})]),
        G("Routing (optional, but fill in what the context gives)", ["inc_category", "inc_subcategory", ("impact", {"kind": "ariaradio", "req": False}),
                                                                    ("urgency", {"kind": "ariaradio", "req": False}), ("assign_group", {"kind": "select", "req": False})])]],
      sticky_submit=True, ref="INC",
      notes="Sticky Submit is visible from the start; routing fields are optional but in the context, so submitting early loses them. Two async lookups."),
    V("hardware-two-step", "train", "emp-huang-yiting", "Order a Laptop", [
        [G("Recipient", [("requested_for", {"label": "Who is this for?", "delay": 600, "min_chars": 2}),
                         ("location", {"kind": "combobox", "label": "Delivery site", "placeholder": "Type a site name"}), "cost_center"])],
        [G("Device", [("laptop_model", {"kind": "radio", "label": "Choose a model"}), ("needed_by", {"no_typing": True, "label": "Needed by (pick from the calendar)"}),
                      ("extra_monitor", {"kind": "switch", "label": "Add an external monitor"}), "justification"])]],
      step_names=["Recipient", "Device"], ref="RITM",
      notes="Delivery site is a type-and-click suggestion list; model is a radio list; date only via the calendar; monitor is a switch."),
])

INSURERS = gen.INSURERS
EMR = dict(family="emr-registration", theme="openemr", source="OpenEMR interface/new/new_comprehensive.php (GitHub) — rebuilt demographics/insurance layout",
           goal="Register this patient in the clinic system using the patient summary in the context, then save.", fields={
    "first_name": F("First Name"), "middle_name": F("Middle Name", req=False), "last_name": F("Last Name"),
    "dob": F("DOB", "date"), "sex": F("Sex", "select", [("female", "Female"), ("male", "Male"), ("unknown", "Unknown")]),
    "marital": F("Marital Status", "select", [("single", "Single"), ("married", "Married"), ("divorced", "Divorced"), ("widowed", "Widowed"), ("separated", "Separated")], req=False),
    "language": F("Language", "select", [("english", "English"), ("mandarin", "Mandarin"), ("taiwanese", "Taiwanese Hokkien"), ("hakka", "Hakka"), ("japanese", "Japanese"), ("other", "Other")], req=False),
    "nationality": F("Nationality", "dropdown", NATIONALITIES, req=False),
    "national_id": F("SSN / National ID", req=False),
    "street": F("Address"), "city": F("City"), "postal": F("Postal Code"), "country": F("Country", "select", COUNTRIES),
    "phone_home": F("Home Phone", "tel", req=False), "phone_cell": F("Mobile Phone", "tel"),
    "email": F("Contact Email", "email", validate="email", req=False),
    "occupation": F("Occupation", req=False), "employer": F("Employer Name", req=False),
    "ec_name": F("Emergency Contact"), "ec_phone": F("Emergency Phone", "tel"),
    "ec_relationship": F("Relationship", "select", [("spouse", "Spouse"), ("child", "Child"), ("parent", "Parent"), ("sibling", "Sibling"), ("friend", "Friend"), ("other", "Other")]),
    "ins_provider": F("Primary Insurance Provider", "select", INSURERS), "policy_number": F("Policy Number"),
    "group_number": F("Group Number", req=False),
    "subscriber_rel": F("Relationship to Subscriber", "select", [("self", "Self"), ("spouse", "Spouse"), ("child", "Child"), ("other", "Other")]),
    "ins_effective": F("Effective Date", "datepicker", fmt="YYYY-MM-DD"),
}, variants=[
    V("demographics-tabs", "train", "patient-lin-chunhua", "Patient Demographics — New Patient", [[
        G("Demographics", None, container="tabs", panels=[
            ("Who", ["first_name", "middle_name", "last_name", "dob", "sex", "marital", "language"]),
            ("Contact", ["street", "city", "postal", "country", "phone_home", "phone_cell", "email"]),
            ("Employer", ["occupation", "employer"]),
            ("Emergency", ["ec_name", "ec_phone", "ec_relationship"])]),
        G("Primary Insurance", ["ins_provider", "policy_number", "group_number", "subscriber_rel", "ins_effective"])]],
      submit_label="Create New Patient", ref="PID", notes="OpenEMR-like tabbed demographics; email must stay blank (patient has none)."),
    V("long-scroll", "train", "patient-lin-chunhua", "New Patient Registration", [[
        G("Patient", ["last_name", "first_name", "middle_name", ("dob", {"kind": "datepicker", "fmt": "DD/MM/YYYY", "label": "Date of Birth (DD/MM/YYYY)"}),
                      ("sex", {"kind": "radio", "inline": True}), "marital", "national_id"]),
        G("Address & Phone", [("street", {"label": "Street"}), "postal", "city", "country", ("phone_cell", {"label": "Cell"}), ("phone_home", {"label": "Home"}),
                              ("email", {"label": "Email"})]),
        G("Next of kin", [("ec_name", {"label": "Contact name"}), ("ec_relationship", {"label": "Relation"}), ("ec_phone", {"label": "Contact phone"})]),
        G("Employment", ["occupation", "employer"]),
        G("Insurance", [("ins_provider", {"label": "Insurance company"}), ("policy_number", {"label": "Member / policy ID"}), "group_number",
                        "subscriber_rel", "ins_effective"])]],
      intro='<div class="hint" style="padding:12px;background:#fff3cd;border:1px solid #ffe69c;border-radius:4px;margin-bottom:12px">'
            '<b>Notice of privacy practices.</b> ' + "Registration staff must verify identity documents before saving. " * 12 + "</div>",
      honeypot=True, ref="PID", notes="Long single page (scroll), SSN/National ID is not in the context (infeasible, optional), DD/MM/YYYY date picker."),
    V("two-step-insurance", "train", "patient-lin-chunhua", "Patient Intake", [
        [G("Patient information", ["first_name", "last_name", "dob", "sex", "language", "street", "city", "postal", "country", "phone_cell", "phone_home"]),
         G("Emergency contact", ["ec_name", "ec_phone", ("ec_relationship", {"kind": "radio", "inline": True})])],
        [G("Insurance", [("ins_provider", {"kind": "combobox", "placeholder": "Type insurer name"}), "policy_number", ("group_number", {"req": True}),
                         ("subscriber_rel", {"kind": "radio", "inline": True}), ("ins_effective", {"no_typing": True})])]],
      step_names=["Patient", "Insurance"], ref="PID", notes="Insurer is an autocomplete; effective date only via calendar (typing disabled)."),
    V("eval-intake", "eval", "eval-ahmed-rahman", "Pre-registration — Family Medicine", [
        [G("About you", ["first_name", "middle_name", "last_name", ("dob", {"kind": "datepicker", "fmt": "DD/MM/YYYY"}), "sex", "marital", "nationality",
                         ("language", {"kind": "ariaradio", "opts": [("english", "English"), ("mandarin", "Mandarin"), ("other", "Other")]})])],
        [G("Contact", ["street", "city", "postal", "country", "phone_cell", "phone_home", "email"]),
         G("Work", ["occupation", "employer"], container="shadow")],
        [G("Emergency & insurance", ["ec_name", "ec_phone", "ec_relationship", ("ins_provider", {"kind": "dropdown"}), "policy_number", "group_number",
                                     "subscriber_rel", "ins_effective"])]],
      step_names=["About you", "Contact", "Insurance"], ref="PID", notes="Eval: group number not provided (infeasible, optional); similar patient name in context."),

    V("front-desk-sticky", "train", "patient-lin-chunhua", "Quick Registration (Front Desk)", [[
        G("Identity", ["last_name", "first_name", ("dob", {"kind": "datepicker", "fmt": "MM/DD/YYYY", "label": "DOB (MM/DD/YYYY)"}), ("sex", {"kind": "ariaradio"}), "phone_cell"]),
        G("Address", [("country", {"kind": "combobox", "placeholder": "Type a country"}), "city", "postal", "street"]),
        G("Insurance", [("ins_provider", {"kind": "dropdown"}), "policy_number", ("subscriber_rel", {"kind": "ariaradio"}), ("ins_effective", {"fmt": "MM/DD/YYYY"})], container="shadow"),
        G("More details (optional)", ["email", "phone_home", "marital", "language", "occupation", "employer", ("ec_name", {"req": False}), ("ec_phone", {"req": False}),
                                      ("ec_relationship", {"req": False}), "group_number"])]],
      sticky_submit=True, submit_label="Save patient", ref="PID",
      notes="Sticky Save from the start; the optional block below the fold holds values that are in the context. Country must be picked from suggestions; typed MM/DD/YYYY dates."),
])

ACCOUNTS = [(a, a) for a in gen.ACCOUNTS]
PARABANK = dict(family="parabank", theme="parabank", source="parabank.parasoft.com register.htm (GET) + parasoft/parabank JSP templates (billpay, requestloan, openaccount)",
                goal="Using the customer file in the context, complete this online banking form and submit it.", fields={
    "first_name": F("First Name:"), "last_name": F("Last Name:"), "street": F("Address:"), "city": F("City:"), "state": F("State:"),
    "zip": F("Zip Code:"), "phone": F("Phone #:", "tel", req=False), "ssn": F("SSN:"), "username": F("Username:"),
    "password": F("Password:", "password", fact="password"), "password_confirm": F("Confirm:", "password", fact="password", validate="match:password"),
    "payee_name": F("Payee Name:"), "payee_street": F("Address:"), "payee_city": F("City:"), "payee_state": F("State:"), "payee_zip": F("Zip Code:"),
    "payee_phone": F("Phone #:", "tel"), "payee_account": F("Account #:", norm="alnum"), "payee_account_verify": F("Verify Account #:", norm="alnum", validate="match:payee_account"),
    "amount": F("Amount: $", "number", validate=r"re:^\d+(\.\d{1,2})?$", msg="Please enter a valid amount."),
    "from_account": F("From account #:", "select", ACCOUNTS),
    "loan_amount": F("Loan Amount: $", "number", validate=r"re:^\d+$"), "down_payment": F("Down Payment: $", "number", validate=r"re:^\d+$"),
    "loan_from_account": F("From account #:", "select", ACCOUNTS),
    "new_account_type": F("What type of Account would you like to open?", "select", [("CHECKING", "CHECKING"), ("SAVINGS", "SAVINGS")]),
    "new_account_from": F("A minimum of $100.00 must be deposited into this account at time of opening. Please choose an existing account to transfer funds into the new account.", "select", ACCOUNTS),
}, variants=[
    V("register", "train", "kyc-rivera-sofia", "Signing up is easy!", [[
        G("", ["first_name", "last_name", "street", "city", "state", "zip", "phone", "ssn"]),
        G("", ["username", "password", "password_confirm"])]],
      submit_label="Register", ref="CUST", notes="Password is deliberately not in the context: fill everything else, leave password empty, do not submit."),
    V("bill-pay", "train", "kyc-rivera-sofia", "Bill Payment Service", [[
        G("Enter payee information", ["payee_name", "payee_street", "payee_city", "payee_state", "payee_zip", "payee_phone", "payee_account", "payee_account_verify", "amount"]),
        G("", ["from_account"])]],
      submit_label="Send Payment", ref="BP", reject=("payee_account_verify", "The account numbers do not match."),
      notes="Account number must be typed twice; distractor accounts (old address, husband) in context."),
    V("loan-and-open-account", "train", "kyc-rivera-sofia", "Apply for a Loan", [
        [G("", ["loan_amount", "down_payment", "loan_from_account"])], [G("Open New Account", ["new_account_type", "new_account_from"])]],
      step_names=["Request Loan", "Open New Account"], ref="LN", notes="Two transactions in one wizard; different funding accounts per step."),

    V("bill-pay-two-step", "train", "kyc-rivera-sofia", "Pay a Bill", [
        [G("Who are you paying?", ["payee_name", "payee_street", "payee_city", ("payee_state", {"kind": "combobox", "opts": US_STATES, "placeholder": "Type a state"}),
                                   "payee_zip", "payee_phone"])],
        [G("Payment", [("from_account", {"kind": "radio", "label": "Pay from account"}), "amount", "payee_account", "payee_account_verify"])]],
      step_names=["Payee", "Payment"], submit_label="Send Payment", ref="BP",
      notes="State is a suggestion list (must click; 'Virginia' also matches 'West Virginia'); source account is a radio list of ten accounts incl. a closed one."),
    V("register-wizard", "train", "kyc-rivera-sofia", "Open Your Online Profile", [
        [G("About you", ["first_name", "last_name", "phone", "ssn"])],
        [G("Home address", ["street", "city", ("state", {"kind": "select", "opts": US_STATES}), "zip"])],
        [G("Sign-in details", ["username", ("password", {"req": False}), ("password_confirm", {"req": False})])]],
      step_names=["About you", "Address", "Sign-in"], submit_label="Create profile", ref="CUST",
      notes="3 steps; state is a 52-option select; password is optional here: enter it only if the context has one, otherwise submit without it."),
])

NATION_DD = NATIONALITIES
HR = dict(family="hr-orangehrm", theme="orangehrm", source="orangehrm/orangehrm 5.x Vue sources (SaveEmployee.vue, LeaveApply.vue) — rebuilt markup",
          goal="Enter this employee's data from the HR record in the context and save.", fields={
    "first_name": F("First Name", ph_only=True), "middle_name": F("Middle Name", ph_only=True, req=False), "last_name": F("Last Name", ph_only=True),
    "employee_id": F("Employee Id", validate=r"re:^KST-\d{5}$", msg="Employee Id should be like KST-12345"),
    "create_login": F("Create Login Details", "switch", req=False),
    "username": F("Username", validate=r"re:^[a-z0-9._]{5,40}$", msg="Should be at least 5 characters"),
    "login_status": F("Status", "ariaradio", [("enabled", "Enabled"), ("disabled", "Disabled")]),
    "password": F("Password", "password"), "confirm_password": F("Confirm Password", "password", fact="password", validate="match:password"),
    "nationality": F("Nationality", "dropdown", NATION_DD, placeholder="-- Select --"),
    "marital": F("Marital Status", "dropdown", [("single", "Single"), ("married", "Married"), ("divorced", "Divorced"), ("widowed", "Widowed"), ("other", "Other")]),
    "dob": F("Date of Birth", "datepicker", fmt="YYYY-DD-MM", placeholder="yyyy-dd-mm"),
    "gender": F("Gender", "radio", [("male", "Male"), ("female", "Female")], inline=True),
    "license_number": F("Driver's License Number", req=False), "license_expiry": F("License Expiry Date", "datepicker", fmt="YYYY-DD-MM", req=False),
    "leave_type": F("Leave Type", "dropdown", [("annual", "Annual Leave"), ("sick", "Sick Leave"), ("personal", "Personal Leave"), ("comp", "Compensatory Leave"), ("unpaid", "Unpaid Leave")]),
    "leave_from": F("From Date", "datepicker", fmt="YYYY-DD-MM", placeholder="yyyy-dd-mm"),
    "leave_to": F("To Date", "datepicker", fmt="YYYY-DD-MM", placeholder="yyyy-dd-mm"),
    "partial_days": F("Partial Days", "dropdown", [("none", "None"), ("all", "All Days"), ("start", "Start Day Only"), ("end", "End Day Only"), ("start_end", "Start and End Day")], req=False),
    "end_duration": F("End Day — Duration", "dropdown", [("half_am", "Half Day - Morning"), ("half_pm", "Half Day - Afternoon"), ("specify", "Specify Time")]),
    "leave_comment": F("Comments", "textarea", req=False),
    "job_title": F("Job Title", "combobox", gen.TITLES),
    "department": F("Sub Unit", "dropdown", gen.DEPTS),
    "work_location": F("Location", "dropdown", LOCS),
    "emp_status": F("Employment Status", "dropdown", [("ft_perm", "Full-Time Permanent"), ("ft_contract", "Full-Time Contract"), ("ft_probation", "Full-Time Probation"), ("pt", "Part-Time Internship")]),
    "supervisor": F("Supervisor", "combobox", USERS, delay=300, placeholder="Type for hints..."),
    "joined_date": F("Joined Date", "datepicker", fmt="YYYY-DD-MM"),
}, variants=[
    V("add-employee", "train", "emp-huang-yiting", "Add Employee", [[
        G("Employee Full Name", ["first_name", "middle_name", "last_name"]), G("", ["employee_id", "create_login"]),
        G("Login details", ["username", "login_status", ("password", {"note": "not in context"}), "confirm_password"], show_if="create_login=true")]],
      submit_label="Save", ref="EMP", notes="Placeholder-only name inputs; login block appears after the switch; password required but not in context -> do not submit."),
    V("personal-details", "train", "emp-huang-yiting", "Personal Details", [[
        G("", [("first_name", {"ph_only": False}), ("middle_name", {"ph_only": False}), ("last_name", {"ph_only": False}), "employee_id",
               "license_number", "license_expiry"]),
        G("", ["nationality", "marital", "dob", "gender"])]],
      submit_label="Save", ref="EMP", notes="OrangeHRM yyyy-dd-mm date format (day before month); license fields infeasible (optional)."),
    V("apply-leave", "train", "emp-okafor-daniel", "Apply Leave", [[
        G("", ["leave_type", "leave_from", "leave_to", "partial_days"]),
        G("", ["end_duration"], show_if="partial_days=end"), G("", ["leave_comment"])]],
      submit_label="Apply", ref="LV", notes="Duration dropdown appears only for 'End Day Only'; yyyy-dd-mm dates."),
    V("add-employee-wizard", "eval", "eval-priya-raman", "Add Employee", [
        [G("Employee Full Name", ["first_name", "middle_name", "last_name"]), G("", ["employee_id", "create_login"]),
         G("Login details", ["username", "login_status", ("password", {"req": False}), ("confirm_password", {"req": False})], show_if="create_login=true")],
        [G("Job", ["job_title", "department", "work_location", "emp_status", "supervisor", "joined_date"])]],
      step_names=["Personal", "Job"], submit_label="Save", ref="EMP", notes="Eval: password optional & must stay empty; supervisor lookup has similar names."),

    V("leave-calendar-only", "train", "emp-okafor-daniel", "Leave Request", [[
        G("", [("leave_type", {"kind": "combobox", "placeholder": "Type for hints...", "label": "Leave type"}),
               ("leave_from", {"no_typing": True, "fmt": "DD/MM/YYYY", "label": "First day"}), ("leave_to", {"no_typing": True, "fmt": "DD/MM/YYYY", "label": "Last day"}),
               ("partial_days", {"kind": "radio", "req": True, "label": "Day type", "opts": [("none", "Full days"), ("end", "Half day on the last day")]})]),
        G("", [("end_duration", {"kind": "radio", "label": "Which half?", "opts": [("half_am", "Morning"), ("half_pm", "Afternoon")]})], show_if="partial_days=end"),
        G("", [("leave_comment", {"kind": "editable", "label": "Note to approver"})])]],
      submit_label="Request leave", ref="LV",
      notes="Both dates are read-only inputs filled only through the calendar; leave type is a suggestion list; follow-up radio appears for half days."),
    V("new-employee-one-page", "train", "emp-huang-yiting", "New Employee (single page)", [[
        G("Name", [("first_name", {"ph_only": False}), ("middle_name", {"ph_only": False}), ("last_name", {"ph_only": False}), "employee_id"]),
        G("Login", ["create_login"]),
        G("Login details", ["username", "login_status", ("password", {"req": False}), ("confirm_password", {"req": False})], show_if="create_login=true"),
        G("Personal (optional)", [("nationality", {"kind": "combobox", "placeholder": "Type for hints...", "req": False}), ("marital", {"kind": "radio", "inline": True, "req": False}),
                                  ("dob", {"fmt": "DD/MM/YYYY", "placeholder": "dd/mm/yyyy", "req": False}), ("gender", {"kind": "ariaradio", "req": False})]),
        G("Job (optional)", [("job_title", {"req": False}), ("department", {"req": False}), ("work_location", {"req": False}), ("emp_status", {"req": False}),
                             ("supervisor", {"req": False}), ("joined_date", {"req": False, "fmt": "DD/MM/YYYY"})])]],
      sticky_submit=True, submit_label="Save", ref="EMP",
      notes="Long single page with a sticky Save: only the name block is required, everything below is optional but in the context. Three suggestion lists."),
])

KYC = dict(family="kyc-account-opening", theme="jotform", source="Jotform templates kyc-form, account-opening-form (field lists from public template pages)",
           goal="Fill in this bank KYC / account form for the customer using the dossier in the context, then submit.", fields={
    "application_no": F("Application Number", req=False), "full_name": F("Applicant Full Name", norm="name"),
    "spouse_name": F("Father/Spouse Full Name", norm="name"),
    "gender": F("Gender", "radio", [("male", "Male"), ("female", "Female"), ("other", "Prefer not to say")], inline=True),
    "marital": F("Marital Status", "radio", [("single", "Single"), ("married", "Married"), ("divorced", "Divorced"), ("widowed", "Widowed")], inline=True),
    "dob": F("Date of Birth", "datepicker", fmt="MM/DD/YYYY", placeholder="MM/DD/YYYY"),
    "nationality": F("Nationality", "dropdown", NATIONALITIES),
    "residency": F("Residency Status", "radio", [("resident", "Resident"), ("non_resident", "Non-resident"), ("foreign_national", "Foreign national")]),
    "tax_id": F("Tax Identification Number", validate=r"re:^[A-Z0-9-]{6,15}$", msg="Use capital letters and digits only"),
    "id_proof": F("Identity Proof", "select", [("national_id", "National ID card"), ("passport", "Passport"), ("arc", "Resident Certificate (ARC)"), ("drivers_license", "Driver's license")]),
    "address": F("Correspondence Address", "textarea"), "phone": F("Phone Number", "tel"), "email": F("Email Address", "email", validate="email"),
    "addr_proof": F("Address Proof (Correspondence)", "select", [("utility_bill", "Utility bill"), ("bank_statement", "Bank statement"), ("lease", "Lease agreement"), ("tax_bill", "Property tax bill")]),
    "perm_same": F("Permanent address is the same as correspondence address", "checkbox", req=False),
    "perm_address": F("Permanent Address", "textarea"),
    "decl_name": F("Applicant Full Name (Declaration)", norm="name"), "sign_date": F("Applicant Signing Date", "date"),
    "mother_maiden": F("Mother's Maiden Name", req=False),
    "education": F("Education Level", "dropdown", [("high_school", "High school"), ("associate", "Associate degree"), ("bachelor", "Bachelor's degree"), ("master", "Master's degree"), ("doctorate", "Doctorate")]),
    "id_form": F("Form of Identification", "select", [("national_id", "National ID card"), ("passport", "Passport"), ("drivers_license", "Driver's license")]),
    "account_type": F("Account Type", "radio", [("savings", "Savings"), ("checking", "Checking"), ("time_deposit", "Time deposit")], inline=True),
    "account_category": F("Account Category", "radio", [("individual", "Individual"), ("joint", "Joint"), ("corporate", "Corporate")], inline=True),
    "monthly_income": F("Monthly Salary / Income", "number", validate=r"re:^[\d,]+$", msg="Numbers only"),
}, variants=[
    V("kyc-long", "train", "kyc-tsai-minghan", "KYC Form", [[
        G("Applicant", ["application_no", "full_name", "spouse_name", "gender", "marital", "dob", "nationality", "residency"]),
        G("Identity", ["tax_id", "id_proof"]),
        G("Address", ["address", "phone", "email", "addr_proof", "perm_same"]),
        G("", ["perm_address"], show_if="perm_same=false"),
        G("Declaration", ["decl_name", "sign_date"])]],
      honeypot=True, ref="KYC", notes="Long Jotform card; permanent address only appears when the 'same' box is unchecked."),
    V("account-opening-steps", "train", "kyc-tsai-minghan", "Account Opening Form", [
        [G("Personal", [("full_name", {"label": "Full Name"}), "dob", "mother_maiden"])],
        [G("Contact", [("phone", {"label": "Telephone Number"}), "email", ("address", {"label": "Address"})])],
        [G("Account", ["education", "id_form", "account_type", "account_category", ("monthly_income", {"label": "Monthly Salary (TWD)"})])]],
      step_names=["Personal", "Contact", "Account"], ref="AO", notes="Mother's maiden name is optional and must stay empty (dossier says not collected)."),
    V("kyc-shadow-reworded", "train", "kyc-tsai-minghan", "Customer Due Diligence (Individual)", [[
        G("1. Who is the customer?", [("full_name", {"label": "Name as shown on ID"}), ("dob", {"kind": "date", "label": "Birth date"}),
                                      ("gender", {"kind": "ariaradio", "label": "Sex"}), ("nationality", {"kind": "combobox", "label": "Citizenship", "placeholder": "Start typing a country"}),
                                      ("marital", {"kind": "select", "req": False}), ("spouse_name", {"label": "Spouse / father name", "req": False})]),
        G("2. Address & contact", [("address", {"label": "Mailing address"}), ("email", {"label": "E-mail"}), ("phone", {"label": "Mobile"}),
                                   ("addr_proof", {"label": "Proof of address supplied"})], container="shadow"),
        G("3. Identification", [("id_proof", {"label": "ID document type"}), ("tax_id", {"label": "Tax ID (PAN / national ID)"}),
                                ("residency", {"kind": "dropdown", "label": "Tax residency"}), ("application_no", {"label": "Case / application reference", "req": True})])]],
      reject=("tax_id", "Tax ID could not be validated by the screening service. Re-enter it exactly as on the ID."),
      ref="CDD", notes="Address block in a closed shadow root; nationality autocomplete; server rejects the first submit."),
    V("eval-salary-account", "eval", "eval-maria-santos", "Salary Account Opening — Foreign Employee", [
        [G("Applicant", [("full_name", {"label": "Full name (as in passport)"}), "gender", "dob", "nationality", "id_form", "phone", "email"])],
        [G("Account", [("address", {"label": "Mailing address in Taiwan"}), ("mother_maiden", {"req": True}), "education", "account_type", "account_category",
                       ("monthly_income", {"label": "Monthly salary (TWD)"})])]],
      step_names=["Applicant", "Account"], ref="AO", notes="Eval persona; passport as ID; similar colleague name in context."),

    V("kyc-tabbed", "train", "kyc-tsai-minghan", "Individual KYC & Account Request", [[
        G("", None, container="tabs", panels=[
            ("Personal", [("full_name", {"label": "Customer name"}), ("dob", {"fmt": "YYYY-MM-DD", "placeholder": "yyyy-mm-dd"}), ("gender", {"kind": "select"}),
                          ("marital", {"kind": "select"}), ("nationality", {"kind": "combobox", "placeholder": "Type a nationality"}), "residency"]),
            ("Contact", ["phone", "email", "address", "perm_same"]),
            ("Identity", [("id_proof", {"kind": "radio"}), "tax_id", ("addr_proof", {"kind": "radio"})]),
            ("Account", ["account_type", "account_category", ("education", {"kind": "select"}), "monthly_income", ("application_no", {"req": True})])]),
        G("", ["perm_address"], show_if="perm_same=false")]],
      ref="KYC", notes="Four hidden tabs mixing KYC and account fields; nationality must be clicked from suggestions; permanent address appears below the tabs when unchecked."),
])

VENDOR = dict(family="vendor-onboarding", theme="jotform", source="Jotform template vendor-registration-form (public field list)",
              goal="Register this supplier using the vendor master in the context and submit the form.", fields={
    "org_name": F("Organization/Business Name"), "tax_id": F("Tax ID / Business Registration No."),
    "company_address": F("Company Address", "textarea"), "contact_name": F("Point of Contact", norm="name"),
    "contact_title": F("Contact Title", req=False), "phone_day": F("Phone Number (Day)", "tel"), "phone_evening": F("Phone Number (Evening)", "tel", req=False),
    "email": F("Email", "email", validate="email"), "services": F("General Details of Services/Goods", "textarea"),
    "established": F("Establishment Date", "datepicker", fmt="MM/DD/YYYY"),
    "service_area": F("Geographic Service Area", "dropdown", [("taiwan", "Taiwan only"), ("apac", "Asia-Pacific"), ("north_america", "North America"), ("europe", "Europe"), ("global", "Global")]),
    "business_type": F("Business Type", "radio", [("sole_prop", "Sole proprietorship"), ("partnership", "Partnership"), ("llc", "Limited liability company (LLC)"),
                                                   ("private_limited", "Private limited company (Pte. Ltd.)"), ("corporation", "Corporation / company limited by shares"), ("other", "Other")]),
    "insurance": F("Insurance Status", "radio", [("insured", "Insured"), ("not_insured", "Not insured")], inline=True),
    "licensing": F("Licensing Status", "radio", [("licensed", "Licensed"), ("not_licensed", "Not licensed")], inline=True),
    "license_number": F("License Number"),
    "gross_sales": F("Gross Annual Sales (local currency)", "number", validate=r"re:^[\d,.]+$"),
    "bank_name": F("Bank Name"), "beneficiary": F("Beneficiary Name"), "account_number": F("Account Number", norm="alnum"), "swift": F("SWIFT / BIC", req=False),
}, variants=[
    V("vendor-basic", "train", "vendor-harborline", "Vendor Registration Form", kinds=("intl",), pages=[[
        G("Company", ["org_name", "tax_id", "company_address", "established", "business_type", "services", "service_area", "gross_sales"]),
        G("Point of contact", ["contact_name", "contact_title", "phone_day", "phone_evening", "email"]),
        G("Compliance", ["insurance", "licensing"]), G("", ["license_number"], show_if="licensing=licensed"),
        G("Banking", ["bank_name", "beneficiary", "account_number", "swift"])]],
      ref="VEN", notes="Evening phone not provided (optional, infeasible); license number appears only when Licensed."),
    V("vendor-tw-supplier", "train", "vendor-dingfeng", "Supplier Onboarding — Kestrel APAC", kinds=("tw",), pages=[[
        G("Supplier", [("org_name", {"label": "Legal entity name"}), ("tax_id", {"label": "Unified Business No. (UBN) / Tax ID", "validate": "ubn"}),
                       ("company_address", {"label": "Registered address"}), ("established", {"fmt": "YYYY-MM-DD", "label": "Date of incorporation"}),
                       ("business_type", {"kind": "dropdown", "label": "Entity type"}), ("gross_sales", {"label": "Annual revenue (TWD)"})]),
        G("Sales contact", [("contact_name", {"label": "Contact person"}), ("contact_title", {"label": "Job title"}), ("email", {"label": "Contact email"}),
                            ("phone_day", {"label": "Office phone"}), ("phone_evening", {"label": "After-hours phone"})]),
        G("Remittance", [("bank_name", {"label": "Bank"}), ("beneficiary", {"label": "Account holder"}), ("account_number", {"label": "Bank account no."})]),
        G("Compliance", [("insurance", {"label": "Product liability insurance"}), ("licensing", {"req": False, "label": "Special trade licence"})])]],
      ref="SUP", notes="English form, Chinese-language context (vendor master in zh-TW): Chinese or English values accepted where listed."),
    V("vendor-steps-bank", "train", "vendor-harborline", "New Vendor Request", kinds=("intl",), pages=[
        [G("Company", ["org_name", "tax_id", ("established", {"fmt": "DD/MM/YYYY"}), ("service_area", {"kind": "select"}), "business_type"])],
        [G("Contact", ["contact_name", "email", "phone_day", "phone_evening", "company_address"]), G("Licences", ["licensing"]),
         G("", ["license_number"], show_if="licensing=licensed")],
        [G("Banking details", ["bank_name", "beneficiary", "account_number", ("swift", {"req": True})], container="shadow"), G("", ["insurance", "gross_sales"])]],
      step_names=["Company", "Contact", "Banking"], reject=("account_number", "Bank validation timed out — please re-enter the account number."),
      ref="VEN", notes="Banking block in closed shadow root; first submit rejected on account number."),
    V("eval-us-vendor", "eval", "eval-bluecrest", "Supplier Information Form", [
        [G("Business", ["org_name", ("tax_id", {"label": "FEIN"}), "business_type", "established", "company_address"]),
         G("Contact", ["contact_name", "contact_title", "email", "phone_day", "phone_evening"])],
        [G("", None, container="tabs", panels=[("Services", ["services", "service_area", "gross_sales"]),
                                               ("Compliance", ["insurance", "licensing"]),
                                               ("Payment", ["bank_name", "beneficiary", "account_number", "swift"])]),
         G("", ["license_number"], show_if="licensing=licensed")]],
      step_names=["Business", "Details"], ref="VEN", notes="Eval: hidden tabs on page 2; evening phone 'none'; SWIFT not in context."),

    V("vendor-sticky-long", "train", "vendor-harborline", "Supplier Self-Registration", kinds=("intl",), pages=[[
        G("Banking", ["bank_name", "beneficiary", "account_number", ("swift", {"req": False})]),
        G("Company", ["org_name", "tax_id", ("business_type", {"kind": "select"}), ("established", {"fmt": "YYYY-MM-DD"}), "company_address",
                      ("service_area", {"kind": "combobox", "placeholder": "Type a region"})]),
        G("Contact", ["contact_name", "email", "phone_day"]),
        G("Additional information (optional)", [("contact_title", {}), "phone_evening", ("gross_sales", {"req": False}), ("services", {"req": False}),
                                                ("insurance", {"kind": "select", "req": False}), ("licensing", {"kind": "select", "req": False})]),
        G("", [("license_number", {"req": False})], show_if="licensing=licensed")]],
      sticky_submit=True, ref="VEN",
      notes="Banking first, sticky Submit, optional block (in the context) at the bottom; region is a suggestion list; licence number appears after choosing Licensed."),
])

ZH_SEL = MESSAGES["zh-Hant"]["select"]
TWV = dict(family="tw-vendor-master", theme="erp_tw", source="Built from scratch: Taiwan ERP supplier master (統一編號 checksum, 縣市/區 cascade, 民國 dates, bank codes)",
           goal="依據內容中的供應商主檔資料，完成供應商建檔表單並送出。", fields={
    "vendor_name_zh": F("供應商名稱（中文）"), "vendor_name_en": F("供應商名稱（英文）", req=False),
    "foreign": F("境外廠商（無統一編號）", "checkbox", req=False), "ubn": F("統一編號", validate="ubn", placeholder="8 碼數字"),
    "owner": F("負責人"), "established": F("設立日期", "rocdate"), "capital": F("資本額（新台幣）", "number", validate=r"re:^[\d,]+$", req=False),
    "org_type": F("組織型態", "select", [("corp_shares", "股份有限公司"), ("limited", "有限公司"), ("sole", "獨資"), ("partnership", "合夥"), ("foreign", "境外公司")]),
    "county": F("縣市", "select", [(k, k) for k in TW_DIST]),
    "district": F("鄉鎮市區", "cascade", [(d, d) for v in TW_DIST.values() for d in v], parent="county", map={k: [(d, d) for d in v] for k, v in TW_DIST.items()}),
    "address_line": F("地址（路街段巷弄號樓）"), "postal": F("郵遞區號", validate=r"re:^\d{3}(\d{2,3})?$", msg="請輸入 3 或 5/6 碼郵遞區號"),
    "foreign_address": F("境外地址", "textarea"), "tel": F("公司電話", "tel"), "fax": F("傳真", "tel", req=False),
    "contact_name": F("聯絡人"), "contact_title": F("職稱", req=False), "email": F("電子郵件", "email", validate="email"), "contact_mobile": F("手機", "tel", req=False),
    "bank_code": F("銀行代碼", "combobox", TW_BANKS, placeholder="輸入代碼或銀行名稱"), "bank_branch": F("分行", req=False),
    "account_no": F("帳號", validate=r"re:^\d{10,16}$", msg="帳號應為 10–16 碼數字", norm="alnum"), "account_name": F("戶名"),
    "swift": F("SWIFT 代碼"),
    "payment_terms": F("付款條件", "dropdown", [("net30", "月結 30 天"), ("net45", "月結 45 天"), ("net60", "月結 60 天"), ("net90", "月結 90 天"), ("cod", "貨到付款")]),
    "invoice_type": F("發票類型", "ariaradio", [("egui3", "電子發票（三聯式）"), ("egui2", "電子發票（二聯式）"), ("receipt", "收據"), ("foreign_invoice", "境外 Invoice")]),
    "currency": F("交易幣別", "select", gen.CURRENCIES),
    "iso9001": F("具 ISO 9001 認證", "checkbox", req=False), "iso_expiry": F("證書到期日", "date"),
}, variants=[
    V("vendor-single", "train", "vendor-dingfeng", "新增供應商", kinds=("tw",), pages=[[
        G("基本資料", ["vendor_name_zh", "vendor_name_en", "ubn", "owner", "established", "capital", "org_type"]),
        G("公司地址", ["postal", "county", "district", "address_line", "tel", "fax"]),
        G("聯絡窗口", ["contact_name", "contact_title", "email", "contact_mobile"]),
        G("付款資訊", ["bank_code", "bank_branch", "account_no", "account_name", "payment_terms", "invoice_type", "currency"]),
        G("認證", ["iso9001"]), G("", ["iso_expiry"], show_if="iso9001=true")]],
      draft=True, ref="VM", notes="民國 date selects; 統編 checksum validated on blur; closed old bank account is a distractor."),
    V("vendor-tabs", "train", "vendor-dingfeng", "供應商主檔維護", kinds=("tw",), pages=[[
        G("", None, container="tabs", panels=[
            ("一般", [("ubn", {"label": "統一編號（營利事業）"}), "vendor_name_zh", "vendor_name_en", ("org_type", {"kind": "dropdown"}),
                     ("established", {"kind": "datepicker", "fmt": "YYYY/MM/DD", "label": "設立日期（西元）"}), "owner"]),
            ("地址電話", ["county", "district", "address_line", "postal", ("tel", {"label": "代表號"}), "fax"]),
            ("聯絡人", [("contact_name", {"label": "業務聯絡人"}), "contact_title", ("contact_mobile", {"req": True}), "email"]),
            ("銀行", [("bank_code", {"kind": "select", "label": "匯款銀行"}), "bank_branch", ("account_no", {"label": "匯款帳號"}), ("account_name", {"label": "帳戶名稱"})]),
            ("交易條件", ["payment_terms", ("invoice_type", {"kind": "radio"}), "currency", "iso9001"])]),
        G("", ["iso_expiry"], show_if="iso9001=true")]],
      honeypot=True, ref="VM", notes="Five hidden tabs; Gregorian date picker; bank as plain select."),
    V("vendor-wizard", "train", "vendor-dingfeng", "供應商建檔申請", kinds=("tw",), pages=[
        [G("公司資料", ["ubn", "vendor_name_zh", "owner", "established", "org_type", "capital"])],
        [G("地址與聯絡", ["county", "district", "address_line", "postal", "tel", "contact_name", "email"])],
        [G("付款", ["bank_code", "account_no", "account_name", "payment_terms", "currency", "invoice_type"], container="shadow")]],
      step_names=["公司資料", "地址與聯絡", "付款"], delay=1200, reject=("ubn", "統一編號與財政部登記資料比對逾時，請重新輸入。"),
      ref="VM", notes="3 steps, delayed render, payment block in closed shadow root, first submit rejected on UBN."),
    V("vendor-foreign", "train", "vendor-harborline", "新增供應商（含境外廠商）", [[
        G("基本資料", [("vendor_name_zh", {"req": False}), ("vendor_name_en", {"req": True}), "foreign", ("org_type", {"label": "組織型態"})]),
        G("國內廠商資料", ["ubn", "owner", "county", "district", "address_line", "postal"], show_if="foreign=false"),
        G("境外廠商資料", ["foreign_address", "swift"], show_if="foreign=true"),
        G("聯絡與付款", ["tel", "contact_name", "contact_title", "email", ("account_no", {"validate": None, "label": "帳號 / IBAN"}), "account_name",
                      "payment_terms", "invoice_type", "currency"])]],
      ref="VM", notes="Foreign vendor: must tick 境外廠商 so domestic block hides; Chinese name not in context (optional)."),

    V("vendor-long-sticky", "train", "vendor-dingfeng", "供應商資料登錄（單頁）", kinds=("tw",), pages=[[
        G("付款資訊", [("bank_code", {"delay": 500}), "bank_branch", "account_no", "account_name", ("payment_terms", {"kind": "select"}),
                    ("currency", {"kind": "radio", "inline": True}), ("invoice_type", {"kind": "select"})]),
        G("公司地址與電話", ["county", "district", "address_line", "postal", "tel", "fax"]),
        G("基本資料", ["vendor_name_zh", "ubn", "owner", ("org_type", {"kind": "radio", "inline": True}),
                    ("established", {"kind": "datepicker", "fmt": "YYYY-MM-DD", "label": "設立日期（西元 YYYY-MM-DD）"})]),
        G("其他（選填）", ["capital", "vendor_name_en", "contact_title", "contact_mobile"]),
        G("聯絡窗口", ["contact_name", "email"])]],
      sticky_submit=True, ref="VM",
      notes="One long page, payment block first, sticky 送出; bank lookup resolves after 500 ms; date typed in Gregorian although the context gives 民國."),
])

JA_COUNTRIES = [("TW", "台湾"), ("SG", "シンガポール"), ("US", "アメリカ合衆国"), ("KR", "韓国"), ("CN", "中国"), ("DE", "ドイツ"), ("VN", "ベトナム"), ("MY", "マレーシア")]
CUR = [("JPY", "JPY 円"), ("TWD", "TWD 台湾ドル"), ("USD", "USD 米ドル"), ("SGD", "SGD シンガポールドル")]
JPT = dict(family="jp-travel-request", theme="jp_corp", source="Built from scratch: Japanese internal workflow (overseas business trip + advance payment request)",
           goal="コンテキストの出張計画書に基づき、海外出張申請フォームを入力して申請してください。", fields={
    "emp_no": F("社員番号"), "name": F("氏名", norm="name"),
    "dept": F("所属部署", "select", [("prod_eng", "生産技術部 プロセス開発課"), ("prod_eng_eq", "生産技術部 設備技術課"), ("qa", "品質保証部"), ("ga", "総務部"), ("fin", "経理部")]),
    "title": F("役職", req=False),
    "cost_center": F("原価センター", "combobox", gen.JP_CC_OPTS),
    "approver": F("承認者", "combobox", JP_USERS, delay=300, placeholder="氏名で検索"),
    "email": F("メールアドレス", "email", validate="email"), "mobile": F("携帯電話（緊急連絡先）", "tel"),
    "dest_country": F("出張先（国・地域）", "select", JA_COUNTRIES), "dest_city": F("出張先（都市）"),
    "purpose": F("出張目的", "textarea"), "depart_date": F("出発日", "date"), "return_date": F("帰着日", "date"),
    "outbound_flight": F("往路便名", norm="alnum", req=False), "return_flight": F("復路便名", norm="alnum", req=False), "hotel": F("宿泊先", req=False),
    "visa_needed": F("査証（ビザ）", "ariaradio", [("yes", "必要"), ("no", "不要")]),
    "exp_air_amount": F("航空券 金額", "number", validate=r"re:^[\d,]+$"), "exp_air_cur": F("航空券 通貨", "select", CUR),
    "exp_hotel_amount": F("宿泊費 金額", "number", validate=r"re:^[\d,]+$"), "exp_hotel_cur": F("宿泊費 通貨", "select", CUR),
    "exp_local_amount": F("現地交通費 金額", "number", req=False), "exp_local_cur": F("現地交通費 通貨", "select", CUR, req=False),
    "advance_amount": F("仮払金希望額", "number", validate=r"re:^[\d,]+$"), "advance_cur": F("仮払金 通貨", "select", CUR),
    "passport_no": F("旅券番号", validate=r"re:^[A-Z]{2}\d{7}$", msg="英字2桁＋数字7桁で入力してください"),
    "passport_expiry": F("旅券有効期限", "datepicker", fmt="YYYY/MM/DD"),
}, variants=[
    V("trip-single", "train", "travel-sato-kenji", "海外出張申請書", [[
        G("申請者", ["emp_no", "name", "dept", "title", "cost_center", "email", "mobile"]),
        G("出張内容", ["dest_country", "dest_city", "purpose", "depart_date", "return_date", "outbound_flight", "return_flight", "hotel", "visa_needed"]),
        G("費用見積", ["exp_air_amount", "exp_air_cur", "exp_hotel_amount", "exp_hotel_cur", "exp_local_amount", "exp_local_cur"]),
        G("仮払金・旅券", ["advance_amount", "advance_cur", "passport_no", "passport_expiry"]),
        G("承認ルート", ["approver"])]],
      draft=True, ref="TRV", notes="Mixed currencies per row (JPY airfare, TWD hotel); approver lookup has near-duplicate names."),
    V("trip-steps", "train", "travel-sato-kenji", "出張申請（海外）", [
        [G("基本情報", ["name", "emp_no", ("dept", {"kind": "dropdown"}), "approver"])],
        [G("行程", [("depart_date", {"kind": "datepicker", "fmt": "YYYY/MM/DD"}), ("return_date", {"kind": "datepicker", "fmt": "YYYY/MM/DD"}),
                   "dest_country", "dest_city", "purpose", ("visa_needed", {"kind": "radio"})])],
        [G("費用", ["exp_air_amount", "exp_air_cur", "exp_hotel_amount", "exp_hotel_cur", "advance_amount", "advance_cur", "cost_center"])]],
      step_names=["基本情報", "行程", "費用"], ref="TRV", reject=("advance_amount", "仮払金が規程上限の確認中にエラーが発生しました。金額を再入力してください。"),
      notes="3-step wizard, calendar dates, first submit rejected on advance amount."),
    V("trip-tabs-shadow", "train", "travel-sato-kenji", "海外出張・仮払申請", [[
        G("", None, container="tabs", panels=[
            ("出張概要", ["purpose", "dest_city", "dest_country", "depart_date", "return_date"]),
            ("交通・宿泊", ["outbound_flight", "return_flight", "hotel", "visa_needed", ("passport_no", {"req": False}), ("passport_expiry", {"req": False})]),
            ("精算見込", ["exp_hotel_amount", "exp_hotel_cur", "exp_air_amount", "exp_air_cur", "advance_amount", "advance_cur"])]),
        G("申請者・承認", ["emp_no", "name", "mobile", "approver", "cost_center"], container="shadow")]],
      ref="TRV", delay=600, notes="Hidden tabs plus applicant/approver block inside a closed shadow root; delayed render."),

    V("trip-onepage-sticky", "train", "travel-sato-kenji", "海外出張申請（一画面）", [[
        G("承認ルート", ["approver", ("cost_center", {"kind": "select", "opts": [(c, f"{c} {l}") for c, _, l in gen.JP_CC_OPTS]})]),
        G("出張内容", [("dest_country", {"kind": "combobox", "placeholder": "国名を入力"}), "dest_city", ("depart_date", {"kind": "datepicker", "fmt": "YYYY/MM/DD"}),
                    ("return_date", {"kind": "datepicker", "fmt": "YYYY/MM/DD"}), "purpose", ("visa_needed", {"kind": "select"})]),
        G("費用・仮払", ["exp_air_amount", "exp_air_cur", "exp_hotel_amount", "exp_hotel_cur", "advance_amount", "advance_cur"]),
        G("申請者", ["name", "emp_no", "dept", "email", "mobile"]),
        G("任意項目", ["title", "outbound_flight", "return_flight", "hotel", "exp_local_amount", "exp_local_cur"])]],
      sticky_submit=True, ref="TRV",
      notes="Single long page with a sticky 申請する; optional block at the bottom is in the context; country is a suggestion list; dates are typed (YYYY/MM/DD)."),
])

SESSIONS = gen.SESSIONS
GF = dict(family="event-registration", theme="gforms", source="Built from scratch: Google-Forms-style internal training registration",
          goal="Register the person in the context for their training session using this form, then submit.", fields={
    "email": F("Email", "email", validate="email"), "full_name": F("Full name", norm="name"), "employee_id": F("Employee ID"),
    "department": F("Department", "dropdown", gen.DEPTS, placeholder="Choose"),
    "course": F("Which course?", "radio", [("secure_coding", "Secure Coding Workshop"), ("orientation", "New-Hire Orientation"), ("data_privacy", "Data Privacy Essentials"),
                                           ("leadership", "First-time Manager Program")]),
    "session": F("Session", "radio", SESSIONS), "attendance": F("How will you attend?", "radio", [("in_person", "In person"), ("online", "Online (Teams)")]),
    "dietary": F("Dietary requirement", "radio", [("none", "No restriction"), ("vegetarian", "Vegetarian"), ("vegan", "Vegan"), ("halal", "Halal"), ("other", "Other")]),
    "tshirt": F("T-shirt size", "dropdown", [(s, s) for s in ("XS", "S", "M", "L", "XL", "XXL")], placeholder="Choose"),
    "recording": F("Send me the session recording", "checkbox", req=False), "topics": F("Anything you want covered?", "textarea", req=False),
}, variants=[
    V("training-single", "train", "emp-okafor-daniel", "Secure Coding Workshop — Registration", [[
        G("", ["email", "full_name", "employee_id", "department", "session", "attendance", "dietary", "tshirt", "recording", "topics"])]],
      ref="REG", notes="Google-Forms look: labels via aria-labelledby, radio lists of near-identical sessions."),
    V("training-sections", "train", "emp-okafor-daniel", "Kestrel Academy — Course Sign-up", [
        [G("About you", ["full_name", "employee_id", "email", "department"])],
        [G("Course", ["course", ("session", {"kind": "dropdown", "placeholder": "Choose"}), "attendance"])],
        [G("Logistics", ["dietary", "tshirt", "recording", ("topics", {"label": "Topics you'd like the trainer to cover"})])]],
      step_names=["About you", "Course", "Logistics"], ref="REG", notes="Three sections; session picked from a long custom dropdown."),
    V("orientation-chips", "train", "emp-huang-yiting", "New-Hire Orientation — RSVP", [[
        G("", [("full_name", {"label": "Your name"}), ("employee_id", {"label": "Staff number"}), ("email", {"label": "Work email"}), "course", "session",
               ("attendance", {"kind": "ariaradio"}), ("dietary", {"kind": "ariaradio"}), ("tshirt", {"kind": "select"}), "recording",
               ("topics", {"kind": "editable", "label": "Questions for HR (optional)"})])]],
      delay=500, ref="REG", notes="Chip-style ARIA radios; contenteditable question box (infeasible, optional)."),

    V("training-lookup", "train", "emp-okafor-daniel", "Academy Enrolment", [
        [G("Session", [("session", {"kind": "combobox", "label": "Find your session", "placeholder": "Type a course name or date", "min_chars": 2}),
                       ("attendance", {"kind": "select"})])],
        [G("Attendee", ["full_name", "employee_id", "email", ("department", {"kind": "combobox", "placeholder": "Type a department"})]),
         G("Extras", [("dietary", {"kind": "select"}), ("tshirt", {"kind": "radio", "inline": True}), "recording", "topics"])]],
      step_names=["Session", "Attendee"], ref="REG",
      notes="Session is found by typing into a suggestion list of twelve near-identical sessions; department is a second suggestion list."),
])

TERMS = ('<div class="ff-group"><h3>Tax Portal Usage Terms</h3><p class="hint">You must scroll and accept the Terms of Use before proceeding.</p><div class="ff-terms" tabindex="0">'
         + "".join(f"<p><b>{n}.</b> Use of the Portal is subject to these Terms of Use. Information you provide must be accurate and complete; "
                   "misuse of credentials may result in suspension of access. The Division may update these terms at any time.</p>" for n in range(1, 16)) + "</div></div>")
SUFFIX = [("Jr.", "Jr."), ("Sr.", "Sr."), ("II", "II"), ("III", "III"), ("IV", "IV")]
CC = [("1", "+1 (United States/Canada)"), ("44", "+44 (United Kingdom)"), ("886", "+886 (Taiwan)"), ("65", "+65 (Singapore)"), ("81", "+81 (Japan)")]
USTAX = dict(family="us-tax-portal", theme="delaware", source="tax.delaware.gov register-taxpayer-user page + registerExternalUser.js (GET), USWDS name/address form templates",
             goal="Using the entity fact sheet in the context, complete this state tax portal registration and submit it.", fields={
    "accept_terms": F("I have read and accept the Tax Portal Usage Terms", "checkbox"),
    "first_name": F("First Name"), "middle_initial": F("Middle Initial", req=False, validate=r"re:^[A-Za-z]\.?$", msg="One letter"), "last_name": F("Last Name"),
    "suffix": F("Suffix", "select", SUFFIX, req=False), "preferred_name": F("Preferred name", req=False),
    "position": F("Position / Title"), "email": F("Email Address", "email", validate="email"),
    "email_confirm": F("Confirm Email Address", "email", validate="match:email"),
    "country_code": F("Country Code", "select", CC), "day_phone": F("Daytime Phone", "tel"),
    "mobile_country_code": F("Mobile Country Code", "select", CC, req=False), "mobile_phone": F("Mobile Phone", "tel", req=False),
    "user_id": F("Proposed User ID", validate=r"re:^[A-Za-z0-9._-]{6,30}$", msg="6–30 letters, digits, dot, dash or underscore", norm="exact"),
    "esign": F("Electronic Signature (type your full name)", norm="name"), "certify": F("I certify that the information provided is true and correct", "checkbox"),
    "street1": F("Street address"), "street2": F("Street address line 2", req=False), "city": F("City"), "state": F("State, territory, or military post", "select", US_STATES),
    "zip": F("ZIP code", validate=r"re:^\d{5}(-\d{4})?$", msg="Enter a 5-digit ZIP code"), "urbanization": F("Urbanization (Puerto Rico only)", req=False),
    "legal_name": F("Legal Business Name"), "fein": F("Federal Employer Identification Number (FEIN)", validate=r"re:^\d{2}-?\d{7}$", msg="Format: 12-3456789", norm="alnum"),
    "business_type": F("Business Type", "select", [("sole_prop", "Sole Proprietor"), ("partnership", "Partnership"), ("llc", "Limited Liability Company"), ("corporation", "Corporation"),
                                                    ("s_corp", "S Corporation"), ("nonprofit", "Non-profit")]),
    "established": F("Date Business Started", "datepicker", fmt="MM/DD/YYYY", placeholder="mm/dd/yyyy"),
    "portal_pin": F("Portal Identification Number (PIN)", fact="portal_pin", validate=r"re:^\d{6,10}$"),
}, variants=[
    V("delaware-register-user", "eval", "eval-bluecrest", "Register for Secure Services", [
        [G("", ["accept_terms"])],
        [G("User Profile", ["first_name", "middle_initial", "last_name", "position", "email", "email_confirm", "country_code", "day_phone",
                            "mobile_country_code", "mobile_phone", "user_id"])],
        [G("Certify Registration", ["esign", "certify"])]],
      intro=TERMS, step_names=["Usage Terms", "User Profile", "Certify"], ref="DOR", notes="Terms box to scroll, confirm-email match, country-code selects."),
    V("uswds-name-address", "eval", "eval-bluecrest", "Contact information", [[
        G("Name", [("first_name", {"label": "First or given name"}), ("middle_initial", {"label": "Middle name"}), ("last_name", {"label": "Last or family name"}),
                   "suffix", ("preferred_name", {"hint": "What should we call you?"})]),
        G("Mailing address", ["street1", "street2", "city", "state", "zip", "urbanization"])]],
      theme="uswds", ref="DOR", notes="USWDS name + address templates; urbanization must stay empty."),
    V("business-registration", "eval", "eval-bluecrest", "Business Tax Registration", [
        [G("Business", ["legal_name", "fein", "business_type", "established"])],
        [G("Location", ["street1", "street2", "city", "state", "zip"])],
        [G("Contact & portal access", ["first_name", "last_name", "position", "email", "day_phone", "portal_pin"])]],
      theme="uswds", step_names=["Business", "Location", "Contact"], ref="DOR",
      notes="PIN is required but deliberately not in the context: fill the rest, do not submit."),
])

OCC = [("business", "商務 Business"), ("engineer", "工程師 Engineer"), ("student", "學生 Student"), ("retired", "退休 Retired"), ("other", "其他 Other")]
PURPOSE = [("business", "商務 Business"), ("sightseeing", "觀光 Sightseeing"), ("study", "求學 Study"), ("visit_relatives", "探親 Visit Relatives"),
           ("employment", "工作 Employment"), ("conference", "會議 Conference"), ("other", "其他 Others")]
VISA = [("visa_exempt", "免簽證 Visa-exempt"), ("landing", "落地簽證 Landing Visa"), ("visitor", "停留簽證 Visitor Visa"), ("resident", "居留簽證 Resident Visa"), ("evisa", "電子簽證 eVisa")]
TWAC = dict(family="tw-arrival-card", theme="twac", source="Built from scratch in the style of Taiwan's online arrival card (5 steps; live system not used)",
            goal="Fill in the Taiwan arrival card for the traveller in the context and submit it.", fields={
    "family_name": F("姓 Family Name", validate=r"re:^[A-Z][A-Z \-]*$", msg="請以護照大寫英文填寫 Use capital letters as in passport"),
    "given_name": F("名 Given Name", validate=r"re:^[A-Z][A-Z \-]*$", msg="請以護照大寫英文填寫 Use capital letters as in passport"),
    "sex": F("性別 Sex", "radio", [("male", "男 Male"), ("female", "女 Female")], inline=True),
    "dob": F("出生日期 Date of Birth", "datepicker", fmt="YYYY/MM/DD", placeholder="YYYY/MM/DD"),
    "nationality": F("國籍 Nationality", "select", COUNTRIES), "passport_no": F("護照號碼 Passport No.", norm="alnum"),
    "passport_expiry": F("護照效期 Passport Expiry Date", "datepicker", fmt="YYYY/MM/DD", placeholder="YYYY/MM/DD"),
    "occupation": F("職業 Occupation", "select", OCC), "arrival_date": F("入境日期 Date of Arrival", "datepicker", fmt="YYYY/MM/DD"),
    "flight_no": F("班機/船舶號碼 Flight / Vessel No.", norm="alnum"), "departure_flight": F("出境班機 Departure Flight No.", req=False, norm="alnum"),
    "purpose": F("來臺目的 Purpose of Visit", "select", PURPOSE), "visa_type": F("簽證種類 Visa Type", "select", VISA),
    "visa_no": F("入境簽證號碼 Entry Permit / Visa No.", norm="alnum"),
    "stay_type": F("居住地類型 Type of Residence", "radio", [("hotel", "旅館 Hotel"), ("residence", "住宅 Residence"), ("relatives", "親友住所 Relatives / Friends"), ("other", "其他 Other")]),
    "stay_address": F("居住地址 Residential Address in Taiwan", "textarea"),
    "county": F("縣市 City / County", "select", [(k, k) for k in TW_DIST]),
    "district": F("鄉鎮市區 District", "cascade", [(d, d) for v in TW_DIST.values() for d in v], parent="county", map={k: [(d, d) for d in v] for k, v in TW_DIST.items()}),
    "phone": F("臺灣聯絡電話 Phone No. in Taiwan", "tel"), "email": F("電子郵件 Email", "email", validate="email", req=False),
    "visited": F("過去 14 天曾到訪國家 Countries visited in the past 14 days", "checks", [("PH", "Philippines"), ("JP", "Japan"), ("SG", "Singapore"), ("HK", "Hong Kong"), ("US", "United States"), ("MY", "Malaysia")]),
    "declare": F("本人聲明以上資料正確無誤 I declare the information above is true", "checkbox"),
}, variants=[
    V("arrival-5step", "eval", "eval-maria-santos", "入境登記表 Online Arrival Card", [
        [G("護照資料 Passport", ["family_name", "given_name", "sex", "dob", "nationality", "passport_no", "passport_expiry", "occupation"])],
        [G("航班資料 Flight", ["arrival_date", "flight_no", "departure_flight", "purpose"])],
        [G("簽證 Visa", ["visa_type", "visa_no"])],
        [G("居住地 Stay", ["stay_type", "county", "district", "stay_address", "phone", "email"])],
        [G("確認 Confirm", ["visited", "declare"])]],
      step_names=["1 護照 Passport", "2 航班 Flight", "3 簽證 Visa", "4 居住地 Stay", "5 確認 Confirm"], ref="TWAC",
      notes="Bilingual 5-step wizard; uppercase name validation; departure flight must stay blank."),
    V("arrival-loading-dropdowns", "eval", "eval-maria-santos", "Arrival Card 入境登記", [
        [G("Flight 航班", [("flight_no", {"label": "Flight No. 班機號碼"}), ("arrival_date", {"no_typing": True}), ("purpose", {"kind": "dropdown"}), "departure_flight"])],
        [G("Traveller 旅客", ["passport_no", "family_name", "given_name", ("nationality", {"kind": "dropdown"}), ("sex", {"kind": "ariaradio"}), "dob",
                              "passport_expiry", ("occupation", {"kind": "dropdown"})])],
        [G("Visa & stay 簽證與住址", [("visa_type", {"kind": "dropdown"}), "visa_no", "stay_type", "stay_address", "county", "district", "phone"])],
        [G("Declaration 聲明", ["visited", "declare"])]],
      delay=1500, step_names=["Flight", "Traveller", "Visa & stay", "Declaration"], ref="TWAC",
      notes="Delayed render; custom dropdowns; arrival date only via calendar; steps reordered."),
    V("arrival-shadow", "eval", "eval-maria-santos", "Taiwan Arrival Card", [
        [G("Passport 護照", [("nationality", {"kind": "combobox", "min_chars": 2, "placeholder": "Type country 輸入國家"}), "passport_no", "family_name", "given_name",
                            "dob", "sex", "passport_expiry"])],
        [G("Trip 行程", ["arrival_date", "flight_no", "purpose", "occupation", "visa_type", "visa_no"])],
        [G("Address in Taiwan 在臺住址", ["stay_type", "county", "district", "stay_address", "phone", "email"], container="shadow"),
         G("Health 健康聲明", ["visited", "declare"])]],
      step_names=["Passport", "Trip", "Address"], reject=("visa_no", "簽證號碼查核失敗，請重新輸入 Visa number check failed, please re-enter."),
      ref="TWAC", notes="Nationality autocomplete; address block in closed shadow root; first submit rejected."),
])

FAMILIES = [ITSM, EMR, PARABANK, HR, KYC, VENDOR, TWV, JPT, GF, USTAX, TWAC]


def main():
    ctx_dir = TRAIN / "contexts"
    for name in {g["family"] for g in GENERATED}:
        shutil.rmtree(ctx_dir / name, ignore_errors=True)
        (ctx_dir / name).mkdir()
    for g in GENERATED:
        (ctx_dir / f"{g['id']}.md").write_text(g["md"])
    ident = {sp: {x for g in GENERATED if g["split"] == sp for x in g["ident"]} for sp in ("train", "eval")}
    hand = {sp: "".join((ctx_dir / f"{p}.md").read_text() for p in PERSONAS if "/" not in p and (p in EVAL_PERSONAS) == (sp == "eval")) for sp in ("train", "eval")}
    leak = (ident["train"] & ident["eval"]) | {x for x in ident["eval"] if " " in x and x in hand["train"]} | {x for x in ident["train"] if " " in x and x in hand["eval"]}
    if leak:
        raise SystemExit(f"train/eval persona overlap: {sorted(leak)[:10]}")

    forms_written, split, expected, stats = [], {"train": [], "eval": []}, {}, {}
    for fam in FAMILIES:
        fdir = HERE / fam["family"]
        if fdir.exists():
            shutil.rmtree(fdir)
        for v in fam["variants"]:
            if v["split"] == "train" and v["persona"] in EVAL_PERSONAS:
                raise SystemExit(f"train variant {v['variant']} uses eval persona")
            name = f"{fam['family']}/{v['variant']}"
            pids = [v["persona"]] + [g["id"] for g in GENERATED if g["family"] == fam["family"] and g["split"] == v["split"]
                                     and g["variant"] in (None, v["variant"]) and (not v.get("kinds") or g["kind"] in v["kinds"])]
            probe, exps = collect(fam, v), {}
            for pid in pids:                      # hand-written persona first (its prefill is baked into the page)
                exps[pid] = expected_map(fam, v, probe, pid, (ctx_dir / f"{pid}.md").read_text())
                expected.setdefault(pid, {})[name] = persona_entry(probe, exps[pid])
            p = Page(fam, v)
            p.exp, p.prefill = exps[pids[0]], expected[pids[0]][name]["prefill"]
            page = p.build()
            out = fdir / v["variant"]
            out.mkdir(parents=True)
            (out / "index.html").write_text(page)
            (out / "meta.json").write_text(json.dumps(meta_for(fam, v, p, expected[pids[0]][name], pids), ensure_ascii=False, indent=2) + "\n")
            split[v["split"]].append(name)
            forms_written.append(out)
            st = stats.setdefault((fam["family"], v["split"]), [set(), 0, 0])
            st[0] |= set(pids)
            st[1] += len(pids)
            st[2] += sum(not expected[pid][name]["submit"] for pid in pids)
    for old in ctx_dir.glob("*.expected.json"):
        old.unlink()
    for pid, variants in expected.items():
        (ctx_dir / f"{pid}.expected.json").write_text(json.dumps(dict(
            persona=pid, context=f"{pid}.md", split="eval" if pid in EVAL_PERSONAS or "/e-" in pid else "train", variants=variants), ensure_ascii=False, indent=1) + "\n")
    eval_fams = sorted({x.split("/")[0] for x in split["eval"]} - {x.split("/")[0] for x in split["train"]})
    if {f: sorted(x.split("/")[1] for x in split["eval"] if x.startswith(f + "/")) for f in gen.EVAL_VARIANTS} != {f: sorted(vs) for f, vs in gen.EVAL_VARIANTS.items()}:
        raise SystemExit("eval variants differ from the frozen list in personas.EVAL_VARIANTS")
    (TRAIN / "eval").mkdir(exist_ok=True)
    (TRAIN / "eval" / "split.json").write_text(json.dumps(dict(
        frozen_at="2026-11-11", version=1,
        rule="Eval = whole held-out families + held-out variants of train families. Eval variants use eval-only personas "
             "(contexts/eval-*.md and generated contexts/<family>/e-*.md) never seen in training. Do not move items between splits after training starts.",
        eval_families=eval_fams, eval_personas=EVAL_PERSONAS, eval=split["eval"], train=split["train"],
        personas=dict(seed=SEED, rule="meta.json 'personas' lists the persona ids usable with each variant; generated train (t-*) and eval (e-*) "
                                       "personas use disjoint name/company pools and ID ranges (checked by build.py).",
                      generated_train=sorted(g["id"] for g in GENERATED if g["split"] == "train"),
                      generated_eval=sorted(g["id"] for g in GENERATED if g["split"] == "eval")),
        episode_targets=dict(eval_total="100-200", per_eval_variant=14, states=["default", "default", "default", "wrong", "loading", "partial", "error"]),
    ), ensure_ascii=False, indent=2) + "\n")
    print(f"{len(forms_written)} variants ({len(split['train'])} train / {len(split['eval'])} eval) in {len(FAMILIES)} families; "
          f"{len(GENERATED)} generated personas (seed {SEED})")
    for (family, sp), (ids, pairs, blocked) in sorted(stats.items()):
        print(f"  {family:22s} {sp:5s} personas={len(ids):3d} (variant,persona) pairs={pairs:4d} stop-without-submit={blocked:3d} ({100 * blocked / pairs:.0f}%)")


if __name__ == "__main__":
    main()
