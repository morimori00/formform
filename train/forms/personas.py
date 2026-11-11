"""Deterministic generator of fictional personas (context documents + facts) for the form families.

Used by build.py:  personas, run = generate(seed).  Each persona = {id, family, split, variant, kind, facts, md, ident}.
`facts` has the same shape as build.PERSONAS entries: fact -> (value | [value, *accepted], source_text), where
source_text is a literal substring of `md` (build.py re-checks this). A fact that is absent is infeasible.

Train and eval personas draw names / companies from disjoint pools and numeric IDs from disjoint ranges
(train IDs start with 1-4, eval IDs with 6-9); build.py asserts the identity sets do not intersect.
Everything here is fictional. Choice values must be option values of the pages (build.py fails otherwise).
"""
from __future__ import annotations

import random
from datetime import date, timedelta

MISS = 0.04          # chance that one *required* value is deliberately absent ("stop without submitting")
N_TRAIN, N_EVAL = 40, 8

# ---------------------------------------------------------------- option lists shared with build.py
DEPTS = [("fab_eng", "Fab Engineering"), ("infosec", "Information Security"), ("data_platform", "Data Platform"), ("finance", "Finance"),
         ("hr", "Human Resources"), ("procurement", "Procurement"), ("logistics", "Logistics"), ("quality", "Quality Assurance")]
TITLES = [("data_platform_eng", "Data Platform Engineer"), ("data_platform_lead", "Data Platform Lead"), ("process_int_eng", "Process Integration Engineer"),
          ("sec_analyst", "Senior IT Security Analyst"), ("data_analyst", "Data Analyst"), ("platform_eng", "Platform Engineer"),
          ("yield_eng", "Yield Engineer"), ("equip_eng", "Equipment Engineer"), ("fin_analyst", "Financial Analyst"), ("hr_partner", "HR Business Partner"),
          ("buyer", "Procurement Buyer"), ("logistics_coord", "Logistics Coordinator"), ("qa_eng", "Quality Engineer"), ("soc_analyst", "SOC Analyst")]
LOCS = [("neihu", "Taipei HQ — Neihu"), ("hsp_fab3", "Hsinchu Science Park — Fab 3"), ("hsp_fab2", "Hsinchu Science Park — Fab 2"),
        ("tainan", "Tainan Science Park — Assembly"), ("sg", "Singapore Regional Office")]
COURSES = [("secure_coding", "Secure Coding Workshop"), ("orientation", "New-Hire Orientation"), ("data_privacy", "Data Privacy Essentials"),
           ("leadership", "First-time Manager Program")]
_SESS = [("sc_dec09_am", "secure_coding", "Wed", 9, "09:00–12:30", ""), ("sc_dec09_pm", "secure_coding", "Wed", 9, "13:30–17:00", ""),
         ("sc_dec16_am", "secure_coding", "Wed", 16, "09:00–12:30", ""), ("sc_dec16_pm", "secure_coding", "Wed", 16, "13:30–17:00", ""),
         ("or_dec02_am", "orientation", "Wed", 2, "09:00–12:00", "Hsinchu"), ("or_dec02_pm", "orientation", "Wed", 2, "13:30–16:30", "Taipei"),
         ("or_dec09_am", "orientation", "Wed", 9, "09:00–12:00", "Hsinchu"), ("dp_dec10", "data_privacy", "Thu", 10, "10:00–11:30", ""),
         ("dp_dec10_pm", "data_privacy", "Thu", 10, "14:00–15:30", ""), ("dp_dec17", "data_privacy", "Thu", 17, "10:00–11:30", ""),
         ("ld_dec08", "leadership", "Tue", 8, "09:00–12:00", ""), ("ld_dec15", "leadership", "Tue", 15, "09:00–12:00", "")]
SESSIONS = [(s, f"{dict(COURSES)[c]} — {wd} {d} Dec, {t}" + (f" ({pl})" if pl else "")) for s, c, wd, d, t, pl in _SESS]
INSURERS = [("fmh", "Formosa Mutual Health"), ("hsh", "Harbor Shield Health"), ("pcl", "Pacific Care Life"), ("jmh", "Jade Mountain Health Plan"),
            ("evm", "Evermount Health"), ("nhi", "National Health Insurance only"), ("self_pay", "Self-pay")]
ACCOUNTS = ["13344", "13566", "14010", "15231", "16788", "17452", "18109", "19675", "20346", "21897"]
CURRENCIES = [("TWD", "新台幣 TWD"), ("USD", "美元 USD"), ("SGD", "新加坡幣 SGD"), ("JPY", "日圓 JPY"), ("EUR", "歐元 EUR"), ("MYR", "馬來西亞令吉 MYR"), ("THB", "泰銖 THB")]
JP_DEPTS = [("prod_eng", "生産技術部 プロセス開発課"), ("prod_eng_eq", "生産技術部 設備技術課"), ("qa", "品質保証部"), ("ga", "総務部"), ("fin", "経理部")]
JP_CC = {"prod_eng": ["CC-2210", "CC-2215"], "prod_eng_eq": ["CC-2211"], "qa": ["CC-2300", "CC-2305"], "ga": ["CC-1100"], "fin": ["CC-1200"]}
JP_CC_OPTS = [("CC-2210", "CC-2210", "生産技術部 プロセス開発課"), ("CC-2211", "CC-2211", "生産技術部 設備技術課"), ("CC-2215", "CC-2215", "生産技術部 共通プロジェクト"),
              ("CC-2300", "CC-2300", "品質保証部"), ("CC-2305", "CC-2305", "品質保証部 監査"), ("CC-1100", "CC-1100", "総務部"), ("CC-1200", "CC-1200", "経理部")]
EVAL_VARIANTS = {"itsm-request": ["access-request-wizard"], "emr-registration": ["eval-intake"], "hr-orangehrm": ["add-employee-wizard"],
                 "kyc-account-opening": ["eval-salary-account"], "vendor-onboarding": ["eval-us-vendor"],
                 "us-tax-portal": ["delaware-register-user", "uswds-name-address", "business-registration"],
                 "tw-arrival-card": ["arrival-5step", "arrival-loading-dropdowns", "arrival-shadow"]}

# ---------------------------------------------------------------- pools (train / eval disjoint)
TW_SUR = {"train": ["Wang", "Liu", "Yang", "Wu", "Hsu", "Kuo", "Cheng", "Hsieh", "Chiu", "Liao", "Lai", "Chou", "Yeh", "Su", "Lu", "Chiang", "Tsao", "Fang"],
          "eval": ["Ho", "Kao", "Pan", "Chu", "Peng", "Yu", "Tung", "Fan", "Shih", "Wei"]}
TW_G1 = {"train": ["Yi", "Chia", "Wei", "Shu", "Mei", "Chih", "Chun", "Hsin", "Pei", "Ya", "Tzu", "Kuan", "Cheng", "Jia", "Ming"],
         "eval": ["Po", "Hao", "Yun", "Li", "Yu", "Pin", "Tsung"]}
TW_G2 = {"train": ["Ting", "Ling", "Hua", "Fen", "Hui", "Han", "Wen", "Jie", "Hsuan", "Ying", "Ju", "Lun", "An", "Yen"],
         "eval": ["Chieh", "Hsiang", "Rong", "Kai", "Chi", "Shan", "Ning"]}
INTL_G = {"train": ["Aisha", "Marcus", "Elena", "Tomas", "Nora", "Rahul", "Hannah", "Victor", "Leila", "Oscar", "Ingrid", "Mateo", "Chloe", "Samir",
                    "Julia", "Ethan", "Naomi", "Felix", "Amara", "Lucas", "Irene", "Pavel", "Mina", "Andre"],
          "eval": ["Sophie", "Omar", "Grace", "Hugo", "Anika", "Diego", "Freya", "Ravi", "Clara", "Jonas", "Thandi", "Emil"]}
INTL_S = {"train": ["Novak", "Mensah", "Petrov", "Haddad", "Lindqvist", "Moreau", "Castillo", "Iyer", "Kowalski", "Brennan", "Achebe", "Fischer",
                    "Romano", "Sharma", "Nguyen", "Pham", "Silva", "Costa", "Park", "Ali", "Schmidt", "Bianchi", "Mwangi", "Suzuki"],
          "eval": ["Dubois", "Hoffmann", "Okonkwo", "Bergstrom", "Marino", "Kapoor", "Vasquez", "Yilmaz", "Banerjee", "Ferreira", "Jansen", "Kimura"]}
MIDDLE = {"train": ["James", "Marie", "Lee", "Ann", "Jude", "Rae"], "eval": ["Kai", "Rose", "Noel", "Skye"]}
STEMS = {"train": ["Northwind", "Silverpine", "Redcliff", "Oakhaven", "Stonebridge", "Brightwater", "Ironwood", "Skylark", "Meridian", "Copperfield",
                   "Larkfield", "Windmere", "Halcyon", "Kingsley", "Amberline", "Driftwood", "Seabright", "Thornbury", "Westmark", "Greyfriar",
                   "Highmoor", "Elmstead", "Fairholm", "Lowell"],
         "eval": ["Cobaltview", "Quillon", "Ravenmoor", "Tidewell", "Ashgrove", "Pinnacle", "Wexford", "Marlowe", "Oriel", "Sandhurst", "Vantage", "Yarrow"]}
NAT = [("TW", "Taiwan (R.O.C.)"), ("JP", "Japan"), ("SG", "Singapore"), ("US", "United States"), ("PH", "Philippines"), ("GB", "United Kingdom"),
       ("IN", "India"), ("MY", "Malaysia"), ("VN", "Vietnam"), ("KR", "South Korea"), ("TH", "Thailand"), ("ID", "Indonesia"), ("DE", "Germany"),
       ("NG", "Nigeria"), ("PK", "Pakistan"), ("BD", "Bangladesh")]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
EN_ADDR = [("Taipei City", "Neihu Dist.", "114"), ("Taipei City", "Da'an Dist.", "106"), ("Taipei City", "Xinyi Dist.", "110"),
           ("Taipei City", "Zhongshan Dist.", "104"), ("Taipei City", "Songshan Dist.", "105"), ("Taipei City", "Shilin Dist.", "111"),
           ("New Taipei City", "Banqiao Dist.", "220"), ("New Taipei City", "Xindian Dist.", "231"), ("New Taipei City", "Zhonghe Dist.", "235"),
           ("Hsinchu City", "East Dist.", "300"), ("Hsinchu City", "North Dist.", "300"), ("Taoyuan City", "Zhongli Dist.", "320"),
           ("Taichung City", "Xitun Dist.", "407"), ("Taichung City", "Nantun Dist.", "408"), ("Tainan City", "East Dist.", "701"),
           ("Tainan City", "Yongkang Dist.", "710"), ("Kaohsiung City", "Zuoying Dist.", "813"), ("Kaohsiung City", "Lingya Dist.", "802")]
EN_ROADS = ["Minquan E.", "Zhongxiao E.", "Ren'ai", "Heping W.", "Nanjing E.", "Guangfu", "Zhongshan N.", "Minsheng E.", "Chenggong", "Wenhua",
            "Zhongzheng", "Jianguo", "Fuxing S.", "Dunhua N.", "Ziyou", "Datong"]
US_CITIES = [("San Jose", "CA", "California", "951", "408"), ("Fremont", "CA", "California", "945", "510"), ("Austin", "TX", "Texas", "787", "512"),
             ("Plano", "TX", "Texas", "750", "972"), ("Seattle", "WA", "Washington", "981", "206"), ("Portland", "OR", "Oregon", "972", "503"),
             ("Phoenix", "AZ", "Arizona", "850", "602"), ("Denver", "CO", "Colorado", "802", "303"), ("Chicago", "IL", "Illinois", "606", "312"),
             ("Boston", "MA", "Massachusetts", "021", "617"), ("Raleigh", "NC", "North Carolina", "276", "919"), ("Atlanta", "GA", "Georgia", "303", "404"),
             ("Columbus", "OH", "Ohio", "432", "614"), ("Madison", "WI", "Wisconsin", "537", "608"), ("Albany", "NY", "New York", "122", "518"),
             ("Tampa", "FL", "Florida", "336", "813")]
DE_CITIES = [("Wilmington", "DE", "Delaware", "198", "302"), ("Dover", "DE", "Delaware", "199", "302"), ("Newark", "DE", "Delaware", "197", "302"),
             ("Philadelphia", "PA", "Pennsylvania", "191", "215"), ("Baltimore", "MD", "Maryland", "212", "410"), ("Cherry Hill", "NJ", "New Jersey", "080", "856")]
US_STREETS = ["Alder Creek", "Juniper Hill", "Birchwood", "Stonegate", "Willow Bend", "Quail Hollow", "Marigold", "Copper Ridge", "Larkspur", "Fox Run",
              "Hawthorne", "Meadowlark"]


def long_date(d):
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def kv(rows, table):
    return ["| Field | Value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows] if table else [f"- {k}: {v}" for k, v in rows]


class Run:
    def __init__(self):
        self.used = set()
        self.users = {"train": [], "eval": []}
        self.assets = {"train": [], "eval": []}
        self.jp_users = {"train": [], "eval": []}
        self.managers = {"train": [], "eval": []}
        self.jp_managers = []


class P:
    """One persona under construction."""

    def __init__(self, run, rng, split):
        self.run, self.r, self.split, self.f, self.ident = run, rng, split, {}, []

    def S(self, key, value, text=None):          # record a fact, return the text to put in the document
        if text is None:
            text = value[0] if isinstance(value, list) else value
        self.f[key] = (value, text)
        return text

    def chance(self, x):
        return self.r.random() < x

    def dig(self, n):
        return "".join(self.r.choice("0123456789") for _ in range(n))

    def num(self, n):                            # unique n-digit id; leading digit encodes the split
        while True:
            s = self.r.choice("1234" if self.split == "train" else "6789") + self.dig(n - 1)
            if s not in self.run.used:
                self.run.used.add(s)
                self.ident.append(s)
                return s

    def uniq(self, make):                        # make() -> string; retried until globally unused
        for _ in range(10000):
            s = make()
            if s not in self.run.used:
                self.run.used.add(s)
                self.ident.append(s)
                return s
        raise RuntimeError(f"name pool exhausted near {s!r}")

    def day(self, a, b):
        return a + timedelta(days=self.r.randrange((b - a).days + 1))

    def dt(self, d):                             # a date as an internal document would write it
        return self.r.choice([long_date(d), d.isoformat(), f"{d.day:02d} {MONTHS[d.month - 1][:3]} {d.year}"])

    def person(self, tw=None):
        tw = self.chance(0.6) if tw is None else tw
        s = self.split

        def make():
            if tw:
                return f"{self.r.choice(TW_G1[s])}-{self.r.choice(TW_G2[s])} {self.r.choice(TW_SUR[s])}"
            return f"{self.r.choice(INTL_G[s])} {self.r.choice(INTL_S[s])}"
        first, last = self.uniq(make).split(" ")
        return first, last, tw

    def tw_mobile(self, intl=True):
        a, b, c = self.dig(2), self.dig(3), self.dig(3)
        return f"+886 9{a} {b} {c}" if intl else f"09{a}-{b}-{c}"

    def tw_addr(self):
        city, dist, postal = self.r.choice(EN_ADDR)
        lane = f"Ln. {self.r.randint(2, 280)}, " if self.chance(0.5) else ""
        sec = f"Sec. {self.r.randint(1, 6)}, " if self.chance(0.6) else ""
        return f"{self.r.randint(2, 14)}F, No. {self.r.randint(1, 320)}, {lane}{sec}{self.r.choice(EN_ROADS)} Rd., {dist}", city, postal

    def us_addr(self, cities=US_CITIES):
        city, st, state, zp, area = self.r.choice(cities)
        return f"{self.r.randint(100, 9800)} {self.r.choice(US_STREETS)} {self.r.choice(['Way', 'Dr', 'Ln', 'Ct', 'Ave', 'St'])}", city, st, state, zp + self.dig(2), area

    def us_phone(self, area):
        return f"({area}) 555-01{self.dig(2)}"

    def notes(self, title, items, k=3):
        return ["", f"## {title}"] + [f"- {x}" for x in self.r.sample(items, min(k, len(items)))]


# ================================================================ employee (itsm-request, hr-orangehrm, event-registration)
LAPTOPS = [("std14", 'Standard Laptop 14" (16 GB)'), ("eng16", 'Engineering Workstation Laptop 16" (32 GB)'),
           ("eng16_64", 'Engineering Workstation Laptop 16" (64 GB, GPU)'), ("design14", 'Design Laptop 14" (high-DPI)')]
LAPTOP_WHY = ["New hire in {d} — needs the standard build before day one.", "Replacement for a device with a failed mainboard; {d} work is blocked.",
              "Runs yield analysis tooling (JMP, Python) for {d}.", "Current laptop is out of warranty and cannot run the new {d} toolchain.",
              "Transferred to {d}; previous device stays with the old team.", "Needs GPU for layout rendering during the {d} tape-out review."]
INCIDENTS = [("network", "vpn", "netops", "VPN client fails to connect after the {v} update", "Since the {v} client update the VPN shows error {e} at login. Happens on office Wi-Fi and at home. Reinstalling did not help."),
             ("network", "wifi", "netops", "Wi-Fi drops every few minutes on floor {n}", "Laptop loses the corporate Wi-Fi every 5–10 minutes near meeting room {n}-{e}. Wired dock works. Started this week."),
             ("network", "dns", "netsec", "Internal sites not resolving from guest VLAN {e}", "Names under intra.kestrel-semi.example stopped resolving from VLAN {e} after the firewall change. IP access still works."),
             ("hardware", "laptop", "endpoint", "Laptop battery swollen, trackpad lifting", "The trackpad is lifting and the case no longer closes flat. Battery health reports {e} cycles. Device is powered off for safety."),
             ("hardware", "monitor", "endpoint", "External monitor flickers through dock {e}", "The 27-inch monitor flickers and goes black for a second when connected through dock model {e}. Direct HDMI is fine."),
             ("hardware", "printer", "servicedesk", "Badge printing fails on printer P-{e}", "Secure print jobs stay in the queue on printer P-{e} on floor {n}; badge tap shows 'no jobs'. Other users are affected too."),
             ("software", "email", "servicedesk", "Shared mailbox missing after migration batch {e}", "The team shared mailbox no longer appears in the mail client after migration batch {e}. Web mail shows it with read-only rights."),
             ("software", "os", "endpoint", "Blue screen after patch KB{e}", "Laptop crashes with a stop error about ten minutes after boot since patch KB{e} was installed. Safe mode is stable."),
             ("software", "office", "servicedesk", "Spreadsheet add-in {v} crashes on open", "The finance add-in version {v} crashes the spreadsheet application when opening workbooks larger than {n}0 MB."),
             ("database", "db_access", "dba", "Cannot log in to reporting replica rpt-{n}", "Login to reporting replica rpt-{n} fails with error {e} since the weekend maintenance. Role membership looks unchanged."),
             ("database", "db_perf", "dba", "Nightly load on dw-{n} runs {e} minutes late", "The nightly load on dw-{n} now finishes about {e} minutes later than last month; downstream dashboards miss the 08:00 refresh."),
             ("inquiry", "howto", "servicedesk", "How to request a temporary admin token", "Needs a temporary local admin token for about {n} days to install lab equipment drivers. Asking which form to use.")]
LBL = {"network": "Network", "hardware": "Hardware", "software": "Software", "database": "Database", "inquiry": "Inquiry / Help", "vpn": "VPN",
       "wifi": "Wireless", "dns": "DNS", "laptop": "Laptop", "monitor": "Monitor", "printer": "Printer", "email": "Email", "os": "Operating System",
       "office": "Office apps", "db_access": "Access", "db_perf": "Performance", "howto": "How-to", "servicedesk": "Service Desk",
       "netops": "Network Operations", "netsec": "Network Security", "endpoint": "Endpoint Engineering", "dba": "Database Administration"}
APPS = [("dwh", "Data Warehouse"), ("dwh_stage", "Data Warehouse — Staging"), ("mes", "MES (Manufacturing Execution)"), ("erp", "ERP Finance"),
        ("jira", "Issue Tracker"), ("bi", "BI Dashboards")]
ROLES = [("viewer", "Viewer"), ("analyst", "Analyst"), ("developer", "Developer"), ("admin", "Administrator")]
LEAVE = [("annual", "Annual Leave"), ("sick", "Sick Leave"), ("personal", "Personal Leave"), ("comp", "Compensatory Leave"), ("unpaid", "Unpaid Leave")]
LEAVE_WHY = ["Family travel — handover to {m}", "Medical appointment and recovery", "Moving house; reachable by phone for urgent issues",
             "Wedding of a sibling abroad", "Child's school event — {m} covers approvals", "Rest after the quarter-end close"]
TOPICS = ["Threat modeling for internal tools", "Secrets handling in CI", "How data retention rules apply to lab notebooks", "Giving feedback to senior engineers",
          "Badge and cleanroom access rules", "Handling customer data in test environments", "Delegation without micromanaging"]
STATUS = [("ft_perm", "Full-Time Permanent"), ("ft_contract", "Full-Time Contract"), ("ft_probation", "Full-Time Probation"), ("pt", "Part-Time Internship")]


def gen_employee(p, family):
    r, S, split = p.r, p.S, p.split
    first, last, tw = p.person()
    full = f"{first} {last}"
    mid = r.choice(MIDDLE[split]) if not tw and p.chance(0.35) else ""
    eid = "KST-" + p.num(5)
    uid = "u_g" + eid[4:]
    local = f"{first}.{last}".lower().replace("-", "")
    dept, title, loc, status = r.choice(DEPTS), r.choice(TITLES), r.choice(LOCS), r.choice(STATUS)
    mgr = r.choice(p.run.managers[split])
    p.run.users[split].append((uid, full, f"{local}@ · {dept[1]}"))
    nat = NAT[0] if tw else r.choice(NAT[1:])
    gender, marital = r.choice(["Female", "Male"]), r.choice(["Single", "Single", "Married", "Married", "Divorced", "Widowed"])
    dob, start = p.day(date(1968, 1, 1), date(2002, 12, 31)), p.day(date(2026, 11, 16), date(2027, 2, 26))
    S("full_name", [full, f"{last} {first}"], full)
    S("requested_for", uid, full)
    S("caller", uid, full)
    rows = [("Employee ID", S("employee_id", eid)),
            ("Legal name", f"{full} (given name: {S('first_name', first)}, family name: {S('last_name', last)})"),
            ("Middle name", S("middle_name", mid) if mid else S("middle_name", "", "— (none)")),
            ("Date of birth", "not yet verified — ID copy pending" if family == "hr-orangehrm" and split == "train" and p.chance(MISS) else S("dob", dob.isoformat(), p.dt(dob))),
            ("Gender", S("gender", gender.lower(), gender)), ("Marital status", S("marital", marital.lower(), marital)),
            ("Nationality", S("nationality", nat[0], nat[1]))]
    if p.chance(0.3):
        exp = p.day(date(2027, 3, 1), date(2033, 12, 31))
        rows.append(("Driver's license", f"{S('license_number', 'DL-' + p.num(8))}, expires {S('license_expiry', exp.isoformat())}"))
    else:
        rows.append(("Driver's license", "Not on file — skip license fields"))
    rows += [("Department", S("department", dept[0], dept[1])), ("Job title", S("job_title", title[0], title[1])),
             ("Work location", S("work_location", loc[0], loc[1])), ("Employment status", S("emp_status", status[0], status[1])),
             ("Reports to", f"{S('supervisor', mgr[0], mgr[1])} ({mgr[2]})"), ("Start date", S("joined_date", start.isoformat(), p.dt(start)))]
    if family == "itsm-request" and split == "train" and p.chance(MISS):
        rows.append(("Cost center", "pending — Finance has not assigned one yet"))
    else:
        rows.append(("Cost center", S("cost_center", "CC-" + p.dig(4))))
    street, city, postal = p.tw_addr()
    old, ocity, opostal = p.tw_addr()
    L = [f"# Kestrel Semiconductor Taiwan Ltd. — {r.choice(['HR Employee Master Record', 'Employee Profile & Requests', 'People Operations Packet'])}: {full}",
         f"> CONFIDENTIAL · HR internal use only · HRIS export {p.day(date(2026, 11, 2), date(2026, 11, 10)).isoformat()} · Fictional training data", "",
         "## Master data"] + kv(rows, p.chance(0.5))
    L += ["", "## Contact", f"- Work email: {S('email', local + '@kestrel-semi.example')}", f"- Mobile: {S('mobile', p.tw_mobile())}",
          f"- Current address: {street}, {city} {postal}", f"- Previous address (until {r.randint(2021, 2025)}): {old}, {ocity} {opostal}"]

    if family == "hr-orangehrm":
        L += ["", "## IT provisioning (onboarding checklist)"]
        if p.chance(0.88):
            L.append(f"- {S('create_login', True, 'System login: create an account')} — username `{S('username', local)}`")
            st = ("enabled", "Enabled") if p.chance(0.85) else ("disabled", "Disabled (IT enables it on the start date)")
            L.append(f"- Account status at creation: {S('login_status', *st)}")
            if p.chance(0.88):
                pw = r.choice(["Kestrel", "Wafer", "Fab3", "Onboard"]) + r.choice("!#-") + p.dig(4) + r.choice("abcxyz")
                L.append(f"- Initial password (employee must change it at first login): `{S('password', pw)}`")
            else:
                L.append("- Initial password: issued by IT in person on day one. **Never recorded in HR documents.**")
        else:
            L.append(f"- {S('create_login', False, 'System login: not required')} (badge-only role, no HR system account)")
        if split == "train":
            lt = r.choice(LEAVE)
            d1 = p.day(date(2026, 12, 1), date(2027, 3, 20))
            d2 = d1 + timedelta(days=r.randint(0, 5))
            L += ["", f"## Pending leave request (approved verbally by {mgr[1]}, to be entered in the HR system)",
                  f"- Type: {S('leave_type', lt[0], lt[1])}", f"- From {S('leave_from', d1.isoformat(), long_date(d1))} to {S('leave_to', d2.isoformat(), long_date(d2))}"]
            if p.chance(0.4):
                am = p.chance(0.5)
                half = S("partial_days", "end", f"the last day ({d2.day} {MONTHS[d2.month - 1]}) is a half day")
                L.append(f"- Partial day: {half} — {S('end_duration', 'half_am' if am else 'half_pm', 'morning only' if am else 'afternoon only')}")
            else:
                L.append(f"- {S('partial_days', 'none', 'Partial days: none (full days)')}")
            if p.chance(0.7):
                L.append(f"- Comment for the record: \"{S('leave_comment', r.choice(LEAVE_WHY).format(m=mgr[1]))}\"")
            else:
                L.append("- Comment: none given")

    if family == "itsm-request":
        if split == "train":
            m, dl = r.choice(LAPTOPS), (loc if p.chance(0.75) else r.choice(LOCS))
            nb = p.day(date(2026, 11, 20), date(2027, 1, 29))
            mon = p.chance(0.35)
            L += ["", "## Hardware request (enter in the Service Portal on the employee's behalf)", f"- Item: {S('laptop_model', m[0], m[1])}",
                  f"- {S('location', dl[0], 'Deliver to: ' + dl[1])}", f"- Needed by: {S('needed_by', nb.isoformat(), p.dt(nb))}",
                  f"- {S('extra_monitor', mon, 'External monitor: requested' if mon else 'External monitor: not requested')}",
                  f"- Business justification: \"{S('justification', r.choice(LAPTOP_WHY).format(d=dept[1]))}\""]
        else:
            app, role = r.choice(APPS), r.choice(ROLES)
            lvl = r.choice([("ro", "Read only"), ("rw", "Read/Write"), ("admin", "Admin")])
            nb = p.day(date(2026, 11, 20), date(2027, 1, 29))
            L += ["", "## Access needed (Service Desk request)", f"- {S('request_type', 'app_access', 'Request type: Access to application')}",
                  f"- Application: {S('application', app[0], app[1])} ({S('app_role', role[0], role[1] + ' role')})",
                  f"- {S('access_level', lvl[0], 'Access level: ' + lvl[1])}", f"- Needed by: {S('needed_by', nb.isoformat(), p.dt(nb))}",
                  f"- Justification: \"{S('justification', f'{title[1]} in {dept[1]}; needs {app[1]} for daily work.')}\"",
                  f"- Requested for {full} · {S('opened_for_by', mgr[0], 'Opened on the employee’s behalf by ' + mgr[1])}"]
        cat, sub, grp, short, desc = r.choice(INCIDENTS)
        v = dict(v=f"{r.randint(4, 9)}.{r.randint(0, 9)}", e=r.randint(101, 989), n=r.randint(2, 12))
        tag, oldtag = "KST-NB-" + p.num(5), "KST-NB-" + p.num(5)
        p.run.assets[split] += [(tag, tag, f"Laptop · {last}, {first}"), (oldtag, oldtag, "Laptop · returned to stock")]
        imp, urg = r.choice(["1 - High", "2 - Medium", "3 - Low"]), r.choice(["1 - High", "2 - Medium", "3 - Low"])
        cp = r.choice([("email", "Email"), ("phone", "Phone"), ("self_service", "Self-service"), ("walk_in", "Walk-in"), ("chat", "Chat")])
        L += ["", f"## Open IT issue (to log as an incident, caller: {full})", f"- Short description: \"{S('short_desc', short.format(**v))}\"",
              f"- Details: {S('inc_desc', desc.format(**v))}",
              "- Affected laptop: asset tag not recorded (sticker missing)" if split == "train" and p.chance(MISS) else f"- Affected configuration item (laptop asset tag): {S('ci', tag)}",
              f"- {S('inc_category', cat, 'Category: ' + LBL[cat])} · {S('inc_subcategory', sub, 'Subcategory: ' + LBL[sub])}",
              f"- {S('impact', imp[0], 'Impact: ' + imp)} · {S('urgency', urg[0], 'Urgency: ' + urg)}",
              f"- {S('contact_pref', cp[0], 'Contact preference: ' + cp[1])}", f"- {S('assign_group', grp, 'Assignment group: ' + LBL[grp])}"]
        old_asset = f"Laptop {oldtag} (previous device) was returned to IT on {p.day(date(2026, 5, 1), date(2026, 10, 30)).isoformat()}."
    else:
        old_asset = "Old access badge was returned to Security; new badge is ready at reception."

    if family == "event-registration":
        sid, cid, wd, d, t, pl = r.choice(_SESS)
        wdl = {"Wed": "Wednesday", "Thu": "Thursday", "Tue": "Tuesday"}[wd]
        att = ("in_person", "In person") if p.chance(0.65) else ("online", "Online (Teams)")
        diet = r.choice([("none", "none"), ("none", "none"), ("vegetarian", "Vegetarian"), ("vegan", "Vegan"), ("halal", "Halal")])
        rec = p.chance(0.5)
        L += ["", "## Academy registration (to submit for the employee)",
              f"- Course: {S('course', cid, dict(COURSES)[cid])} — session {S('session', sid, f'{wdl} {d} December 2026, {t}' + (f', {pl}' if pl else ''))}",
              f"- Attendance mode: {S('attendance', *att)}", f"- {S('dietary', diet[0], 'Dietary requirement: ' + diet[1])}",
              "- T-shirt size: not provided yet" if p.chance(MISS) else f"- {S('tshirt', (sz := r.choice(['XS', 'S', 'M', 'L', 'XL', 'XXL'])), 'T-shirt size: ' + sz)}",
              f"- {S('recording', rec, 'Wants the session recording: yes' if rec else 'Session recording: not needed')}"]
        L.append(f"- Topics to cover: \"{S('topics', '; '.join(r.sample(TOPICS, 2)))}\"" if p.chance(0.5) else "- Topics to cover: nothing specific")

    of, ol, _ = p.person(tw)
    oid = "KST-" + p.num(5)
    look = f"{first} {ol}" if p.chance(0.5) else f"{of} {last}"
    if look != full and look not in p.run.used:
        p.run.used.add(look)
        p.run.users[split].append(("u_g" + oid[4:], look, f"{look.lower().replace(' ', '.').replace('-', '')}@ · {r.choice(DEPTS)[1]}"))
        lookline = f"{look} ({oid}, {r.choice(DEPTS)[1]}) is a different employee — do not confuse the two records."
    else:
        lookline = f"Buddy assigned: {of} {ol} ({oid})."
    L += p.notes("Unrelated notes in the same export (not for forms)", [
        lookline, old_asset, f"Parking permit B{r.randint(1, 3)}-{r.randint(100, 399)} renewed until 2027-{r.randint(1, 12):02d}-28.",
        f"Payroll batch PB-2026-{r.randint(11, 12)} closes on the 25th; bank file goes to Finance the next day.",
        f"Emergency contact: {r.choice(INTL_G[split])} {last} (family), {p.tw_mobile()}.", "Team offsite date is still to be confirmed.",
        f"Previous employer (reference check done): {r.choice(STEMS[split])} Wafer Services, {r.randint(2012, 2019)}–2026."], 4)
    return "\n".join(L) + "\n"


# ================================================================ patient (emr-registration)
CLINICS = ["Neihu Riverside Clinic", "Da'an Family Medicine", "Hsinchu Lakeside Clinic", "Zhongshan Community Health Center", "Banqiao Garden Clinic"]
JOBS = ["Retired teacher", "Accountant", "Software engineer", "Nurse", "Shop owner", "Taxi driver", "University lecturer", "Homemaker", "Civil servant", "Chef"]
LANGS = [("mandarin", "Mandarin"), ("english", "English"), ("taiwanese", "Taiwanese Hokkien"), ("hakka", "Hakka"), ("japanese", "Japanese")]
RELS = [("spouse", "Spouse"), ("child", "Child"), ("parent", "Parent"), ("sibling", "Sibling"), ("friend", "Friend")]


def gen_patient(p, family):
    r, S, split = p.r, p.S, p.split
    first, last, tw = p.person(p.chance(0.75))
    mid = r.choice(MIDDLE[split]) if not tw and p.chance(0.3) else ""
    mrn = "MRN-" + p.num(7)
    dob = p.day(date(1940, 1, 1), date(2006, 12, 31))
    sex, marital = r.choice(["Female", "Male"]), r.choice(["Single", "Married", "Married", "Divorced", "Widowed", "Separated"])
    nat = NAT[0] if tw else r.choice(NAT[1:])
    lang = r.choice(LANGS[:2] if split == "eval" else LANGS) if tw else LANGS[1]
    street, city, postal = p.tw_addr()
    old, ocity, opostal = p.tw_addr()
    ins = r.choice(INSURERS[:5])
    eff = p.day(date(2019, 1, 1), date(2026, 10, 1))
    ef, el, _ = p.person(tw)
    rel = r.choice(RELS)
    sub = ("self", "Self") if p.chance(0.75) else r.choice([("spouse", "Spouse"), ("child", "Child"), ("other", "Other")])
    L = [f"# {r.choice(CLINICS)} — Patient Summary (Registration Desk Copy)", "CONFIDENTIAL — Protected health information. Fictional training record.", "",
         f"**Patient:** {last.upper()}, {first}   **{mrn}**   **Printed:** 2026-11-{r.randint(2, 10):02d} by front desk", "", "## Demographics",
         f"- Given name: {S('first_name', first)} · Family name: {S('last_name', last)} · " + (f"Middle name: {S('middle_name', mid)}" if mid else S("middle_name", "", "Middle name: none")),
         f"- {S('sex', sex.lower(), 'Sex: ' + sex)}", f"- Date of birth: {S('dob', dob.isoformat(), p.dt(dob))}",
         f"- Marital status: {S('marital', marital.lower(), marital)}", f"- {S('nationality', nat[0], 'Nationality: ' + nat[1])}",
         f"- {S('language', lang[0], 'Preferred language: ' + lang[1])}",
         f"- National ID: {S('national_id', r.choice('ABCDEFGH') + r.choice('12') + p.num(8))}" if p.chance(0.35) else "- National ID: not recorded at this clinic",
         f"- Street address: {S('street', street)}", f"- City: {S('city', city)} · Postal code: {S('postal', postal)} · {S('country', 'TW', 'Country: Taiwan')}",
         (f"- Home phone: {S('phone_home', '0' + r.choice('234') + '-' + p.dig(4) + '-' + p.dig(4))}" if p.chance(0.5) else f"- {S('phone_home', '', 'Home phone: none')}")
         + (" · Mobile: none — reachable on the home phone only" if p.chance(MISS) else f" · Mobile: {S('phone_cell', p.tw_mobile(False))}"),
         f"- Email: {S('email', (first + '.' + last).lower().replace('-', '') + '@inbox.example')}" if p.chance(0.6) else f"- {S('email', '', 'Email: patient has no email address — leave blank')}"]
    if p.chance(0.7):
        L.append(f"- Occupation: {S('occupation', r.choice(JOBS))} · Employer: {S('employer', r.choice(STEMS[split]) + ' ' + r.choice(['Trading Co.', 'Elementary School', 'Design Studio', 'Logistics Ltd.']))}")
    else:
        L.append(f"- Occupation: {S('occupation', ['Retired', 'Retiree'], 'Retired')} · {S('employer', '', 'Employer: none')}")
    L += ["", "## Emergency contact", f"- {S('ec_name', f'{ef} {last}' if p.chance(0.6) else f'{ef} {el}')} — mobile {S('ec_phone', p.tw_mobile(False))} — {S('ec_relationship', rel[0], 'relationship: ' + rel[1])}",
          "", "## Insurance", f"- Primary insurer: {S('ins_provider', ins[0], ins[1])} (fictional private plan)",
          f"- Policy number: {S('policy_number', ins[0].upper() + '-' + p.num(4) + '-' + p.dig(4))} · " + ("Group number: not provided" if p.chance(0.1) else f"Group number: {S('group_number', 'G-' + p.num(4))}"),
          f"- {S('subscriber_rel', sub[0], 'Subscriber: ' + sub[1])} · Plan effective date: {S('ins_effective', eff.isoformat(), p.dt(eff))}", "- Secondary insurance: none",
          "", "## Clinical snapshot (not needed for registration)", f"- Allergies: {r.choice(['penicillin (rash)', 'none known', 'shellfish', 'latex'])}",
          f"- Active problems: {r.choice(['hypertension', 'type 2 diabetes', 'asthma', 'lower back pain', 'none'])}", f"- Last visit: 2026-{r.randint(3, 10):02d}-{r.randint(1, 28):02d}"]
    of, _, _ = p.person(tw)
    L += p.notes("Front-desk notes (other patients — do not mix up)", [
        f"Next slot: {last.upper()}, {of} (MRN-{p.num(7)}, DOB {p.day(date(1945, 1, 1), date(2000, 1, 1)).isoformat()}) — separate chart.",
        f"Previous address on the old chart: {old}, {ocity} {opostal}.", "Clinic closed 2026-12-25 for system maintenance.", "Lab courier pickup moved to 16:30.",
        f"Former insurer until {eff.year - 1}: {r.choice(INSURERS[:5])[1]}, policy closed."], 3)
    return "\n".join(L) + "\n"


# ================================================================ bank customer (parabank)
PAYEES = ["Northgate Water District", "Cedar Valley Electric", "Summit Ridge Gas", "Harbor Point Broadband", "Pinecrest Waste Services", "Lakeshore Energy Co-op",
          "Redwood Mobile", "Clearwater Insurance Group", "Maple Street Property Mgmt", "Ironbridge Telecom", "Sunfield Solar Leasing", "Granite Peak Water",
          "Bluebonnet Electric", "Foxglove Cable", "Tidewater Gas & Light"]


def gen_bank(p, family):
    r, S = p.r, p.S
    first, last, _ = p.person(False)
    street, city, st, state, zp, area = p.us_addr()
    ostreet, ocity, ost, _, ozp, _ = p.us_addr()
    pstreet, pcity, pst, pstate, pzp, parea = p.us_addr()
    chk, sav, closed = r.sample(ACCOUNTS, 3)
    amt = r.randint(1800, 98000) / 100
    loan = r.choice([5, 8, 10, 12, 15, 20, 25, 30, 40]) * 1000
    down = loan // r.choice([5, 8, 10, 20])
    pacct = f"{p.num(5)}-{p.dig(4)}"
    src, lf, nf, nt = r.choice([chk, chk, sav]), r.choice([chk, sav]), r.choice([chk, sav]), r.choice(["SAVINGS", "CHECKING"])
    of, _, _ = p.person(False)
    S("state", [st, state], f"{city}, {st} {zp}")
    S("payee_state", [pst, pstate], f"{pcity}, {pst} {pzp}")
    S("payee_account_verify", pacct, pacct)
    L = ["# Lumen Commercial Bank USA — Customer File (Retail Onboarding)", f"INTERNAL — CONFIDENTIAL. Fictional customer for training. Branch: {city}, {st}.", "",
         "## Customer profile", f"- Name: {first} {last} (first: {S('first_name', first)}, last: {S('last_name', last)})",
         f"- Home address: {S('street', street)}, {S('city', city)}, {st} {S('zip', zp)}",
         f"- Phone: {S('phone', p.us_phone(area))}" if p.chance(0.85) else "- Phone: not provided",
         f"- SSN: {S('ssn', '9' + p.dig(2) + '-' + p.dig(2) + '-' + p.num(4))} (test-range number)", f"- Date of birth: {p.day(date(1960, 1, 1), date(2001, 1, 1)).isoformat()}",
         "", "## Online banking setup", f"- Requested username: {S('username', (first + '.' + last).lower() + p.dig(2))}",
         f"- Password chosen by the customer on the signed enrolment form: `{S('password', r.choice(['Maple', 'River', 'Cobalt', 'Quartz']) + r.choice('!#-') + p.dig(4))}`"
         if p.chance(0.88) else "- Password: the customer will set it on first login — staff must not choose one",
         f"- Checking account: {chk} · Savings account: {sav}", "", f"## Pending instructions from the customer (call of 2026-11-{r.randint(2, 10):02d})",
         f"1. **Pay a bill** — payee: {S('payee_name', r.choice(PAYEES))}", f"   - Payee address: {S('payee_street', pstreet)}, {S('payee_city', pcity)}, {pst} {S('payee_zip', pzp)}",
         "   - Payee phone: not on the bill" if p.chance(MISS) else f"   - Payee phone: {S('payee_phone', p.us_phone(parea))}",
         f"   - Customer account number with the payee: {S('payee_account', pacct)} (enter it twice where the form asks to verify)",
         f"   - Amount: {S('amount', f'{amt:.2f}', f'${amt:,.2f}')} · {S('from_account', src, 'Pay from account: ' + src)}",
         f"2. **Loan request** — personal loan of {S('loan_amount', str(loan), f'${loan:,}')} with {S('down_payment', str(down), f'${down:,} down payment')}, {S('loan_from_account', lf, 'funded from account ' + lf)}.",
         f"3. **Open a new account** — {S('new_account_type', nt, 'type ' + nt)}, {S('new_account_from', nf, 'initial funding from account ' + nf)}."]
    L += p.notes("Other (do not use)", [f"Old address until {r.randint(2019, 2025)}: {ostreet}, {ocity}, {ost} {ozp}",
                                         f"Account {closed} was closed in 2025 — never use it for transfers.", f"Spouse {of} {last} has a separate customer profile.",
                                         "Branch event \"Small business night\" on 2026-12-03.", "Customer asked about a travel card; follow up in January."], 3)
    return "\n".join(L) + "\n"


# ================================================================ KYC (kyc-account-opening)
EDU = [("high_school", "High school diploma"), ("associate", "Associate degree"), ("bachelor", "Bachelor's degree"), ("master", "Master's degree"), ("doctorate", "Doctorate (PhD)")]


def gen_kyc(p, family):
    r, S, split = p.r, p.S, p.split
    first, last, tw = p.person(p.chance(0.75))
    disp = f"{last} {first}" if tw else f"{first} {last}"
    other = f"{first} {last}" if tw else f"{last} {first}"
    gender = r.choice(["Male", "Female"])
    married = p.chance(0.5)
    sf, sl, _ = p.person(tw)
    rel_name = f"{sl} {sf}" if tw else f"{sf} {sl}"
    dob = p.day(date(1955, 1, 1), date(2003, 12, 31))
    nat = NAT[0] if tw else r.choice(NAT[1:])
    street, city, postal = p.tw_addr()
    addr = f"{street}, {city} {postal}"
    old, ocity, opostal = p.tw_addr()
    nid = (r.choice("ABCDEFGHJK") + r.choice("12") + p.num(8)) if tw else (r.choice("PEMX") + p.num(7) + r.choice("ABC"))
    proof = ("national_id", "national ID card") if tw else r.choice([("passport", "passport"), ("arc", "Resident Certificate (ARC)")])
    idform = ("national_id", "National ID card") if tw else ("passport", "Passport")
    res = ("resident", "Resident individual") if tw else r.choice([("foreign_national", "Foreign national (ARC holder)"), ("non_resident", "Non-resident")])
    ap = r.choice([("utility_bill", "utility bill"), ("bank_statement", "bank statement"), ("lease", "lease agreement"), ("tax_bill", "property tax bill")])
    at = r.choice([("savings", "Savings"), ("checking", "Checking"), ("time_deposit", "Time deposit")])
    ac = ("individual", "Individual") if p.chance(0.8) else ("joint", "Joint")
    edu = r.choice(EDU)
    inc = r.randint(38, 320) * 1000
    sign = p.day(date(2026, 11, 2), date(2026, 11, 10))
    L = ["# Lumen Commercial Bank — KYC Dossier (Relationship Manager Working File)", "Classification: STRICTLY CONFIDENTIAL · Customer due diligence · Fictional training data", "",
         f"Case: KYC-2026-{p.num(6)} · Branch: {city}", "", "## Customer", f"- Full name: {S('full_name', [disp, other], disp)}",
         f"- Father/Spouse name: {S('spouse_name', rel_name)} ({'spouse' if married else 'father'})",
         f"- {S('gender', gender.lower(), 'Gender: ' + gender)} · {S('marital', 'married' if married else 'single', 'Marital status: ' + ('Married' if married else 'Single'))}",
         f"- Date of birth: {S('dob', dob.isoformat(), p.dt(dob))}", f"- {S('nationality', nat[0], 'Nationality: ' + nat[1])} · Residency status: {S('residency', *res)}",
         f"- Tax identification number for intake forms: {S('tax_id', nid)}", f"- Identity proof provided: {S('id_proof', *proof)}", "", "## Contact & address",
         f"- Mobile: {S('phone', p.tw_mobile())}",
         "- Email: customer has none (branch contacts by phone)" if p.chance(MISS) else f"- Email: {S('email', (first + '.' + last).lower().replace('-', '') + '@inbox.example')}",
         f"- Correspondence address: {S('address', [addr + ', Taiwan', addr], addr + ', Taiwan')}"]
    S("decl_name", [disp, other], disp)
    if p.chance(0.7):
        L.append(f"- {S('perm_same', True, 'Permanent address: same as correspondence address')}")
    else:
        ps, pc, pp = p.tw_addr()
        pa = f"{ps}, {pc} {pp}"
        L.append(f"- {S('perm_same', False, 'Permanent address (different from correspondence)')}: {S('perm_address', [pa + ', Taiwan', pa], pa + ', Taiwan')}")
    L += [f"- Address proof provided: {S('addr_proof', *ap)}", "", "## Account request", f"- {S('account_type', at[0], 'Account type: ' + at[1])} · {S('account_category', ac[0], 'Account category: ' + ac[1])}",
          f"- Education level: {S('education', *edu)}", f"- Monthly income: {S('monthly_income', str(inc), f'TWD {inc:,}')}",
          f"- {S('id_form', idform[0], 'Form of identification for the account: ' + idform[1])}",
          f"- Mother's maiden name: {S('mother_maiden', r.choice(TW_SUR[split] if tw else INTL_S[split]))}" if p.chance(0.92 if split == "eval" else 0.6)
          else f"- {S('mother_maiden', '', 'Mother’s maiden name: NOT collected in writing')} (asked verbally per policy) — leave that field blank",
          "", "## Application references", f"- Application number: {S('application_no', 'LCB-AO-2026-' + p.num(5))}", f"- Applicant signing date: {S('sign_date', sign.isoformat())}"]
    L += p.notes("RM notes (not for the form)", [f"Old address until {r.randint(2020, 2025)}: {old}, {ocity} {opostal}.",
                                               f"{rel_name} holds a separate account (no. {p.dig(4)}-{p.dig(2)}-{p.num(6)}); do not link.",
                                               "Customer asked about an FX time deposit in USD — separate product.", "Credit card limit review requested; sent to the Cards team.",
                                               f"Previous passport/ID copy on file expired in {r.randint(2019, 2024)}; replaced."], 3)
    return "\n".join(L) + "\n"


# ================================================================ vendors
SECTORS = [("Freight", "Ocean and air freight forwarding and customs brokerage for semiconductor equipment"), ("Precision Tooling", "Precision jigs, fixtures and spare parts for wafer handling"),
           ("Industrial Gases", "Bulk and specialty gas supply with on-site cylinder management"), ("Cleanroom Supplies", "Cleanroom garments, wipers and consumables"),
           ("Analytics", "Data analytics and demand forecasting consulting"), ("Chemicals", "Specialty wet chemicals and solvent recycling"),
           ("Automation", "Factory automation integration and robot maintenance"), ("Packaging", "ESD-safe packaging and wafer shipping boxes"),
           ("Calibration", "Metrology equipment calibration and certification"), ("IT Services", "Managed network and endpoint support services")]
INTL = {
    "SG": dict(country="Singapore", suffix="Pte. Ltd.", bt="private_limited", reg="UEN", cur="SGD", banks=["Orchid Bay Bank", "Lion City Mercantile Bank"]),
    "MY": dict(country="Malaysia", suffix="Sdn. Bhd.", bt="private_limited", reg="SSM registration no.", cur="MYR", banks=["Selat Mutiara Bank", "Bukit Emas Bank"]),
    "US": dict(country="United States", suffix="LLC", bt="llc", reg="FEIN", cur="USD", banks=["Cascade Federal Bank", "Prairie Union Bank", "Old Mill Savings Bank"]),
    "DE": dict(country="Germany", suffix="GmbH", bt=["llc", "private_limited"], reg="VAT ID", cur="EUR", banks=["Elbtal Handelsbank", "Rheinufer Kreditbank"]),
    "TH": dict(country="Thailand", suffix="Co., Ltd.", bt=["private_limited", "llc"], reg="Juristic person no.", cur="THB", banks=["Chao Phraya Commerce Bank", "Siam Lotus Bank"]),
}
EVAL_US_BANKS = ["Granite State Mutual Bank", "Chesapeake Union Trust"]
AREAS = [("taiwan", "Taiwan only"), ("apac", "Asia-Pacific"), ("north_america", "North America"), ("europe", "Europe"), ("global", "Global")]
TERMS_EN = [("net30", "Net 30"), ("net45", "Net 45"), ("net60", "Net 60"), ("net90", "Net 90"), ("cod", "Cash on delivery")]


def gen_vendor_intl(p, family):
    r, S, split = p.r, p.S, p.split
    cc = "US" if split == "eval" else r.choice(list(INTL))
    c = INTL[cc]
    sector, services = r.choice(SECTORS)
    name = p.uniq(lambda: f"{r.choice(STEMS[split])} {sector} {c['suffix']}")
    stem = name.split(" ")[0].lower()
    first, last, _ = p.person(False)
    if cc == "SG":
        reg, addr, phone = f"20{p.dig(2)}{p.num(5)}{r.choice('KMZHD')}", f"{r.randint(2, 88)} {r.choice(['Pioneer Crescent', 'Tuas Avenue 4', 'Ubi Road 1', 'Changi South Lane'])}, #0{r.randint(1, 9)}-{r.randint(10, 28)}, Singapore {p.dig(6)}", f"+65 6{p.dig(3)} {p.dig(4)}"
    elif cc == "MY":
        reg, addr, phone = f"20{p.dig(2)}010{p.num(5)}", f"{r.randint(2, 88)}, Jalan Perusahaan {r.randint(1, 9)}, Bayan Lepas, 11900 Penang, Malaysia", f"+60 4-{p.dig(3)} {p.dig(4)}"
    elif cc == "US":
        street, city, st, _, zp, area = p.us_addr(DE_CITIES if split == "eval" else US_CITIES)
        reg, addr, phone = f"{p.dig(2)}-{p.num(7)}", f"{street}, Suite {r.randint(100, 900)}, {city}, {st} {zp}", p.us_phone(area)
    elif cc == "DE":
        reg, addr, phone = f"DE{p.num(9)}", f"{r.choice(['Industriestrasse', 'Hafenweg', 'Am Technologiepark'])} {r.randint(2, 120)}, 01{p.dig(3)} Dresden, Germany", f"+49 351 {p.dig(3)} {p.dig(4)}"
    else:
        reg, addr, phone = f"0{p.num(12)}", f"{r.randint(2, 399)} Bangna-Trad Road, Bang Na, Bangkok 10260, Thailand", f"+66 2 {p.dig(3)} {p.dig(4)}"
    est = p.day(date(1995, 1, 1), date(2022, 12, 31))
    area_ = r.choice(AREAS[1:])
    sales = r.randint(8, 950) * 100000
    bank = r.choice(EVAL_US_BANKS if split == "eval" else c["banks"])
    acct = f"{p.num(3)}-{p.dig(6)}-{p.dig(1)}"
    terms = r.choice(TERMS_EN)
    bt = c["bt"] if cc != "US" or p.chance(0.6) else "corporation"
    if cc == "US" and bt == "corporation":
        name = name.replace("LLC", "Inc.")
        p.ident.append(name)
    btl = {"private_limited": "Private Limited Company", "llc": "Limited Liability Company", "corporation": "Corporation"}[bt[0] if isinstance(bt, list) else bt]
    title = r.choice(["Commercial Manager", "Sales Director", "Account Manager", "Controller", "Key Account Executive"])
    hon = r.choice(["Ms.", "Mr."])
    S("vendor_name_en", name)
    S("foreign_address", addr)
    S("tel", phone)
    S("account_name", name)
    S("account_no", acct)
    S("org_type", "foreign", c["country"])
    L = [f"# Vendor Master — New Supplier Pack: {name}", "Procurement · Kestrel Semiconductor (APAC) · Confidential · Fictional data for training",
         f"Ticket PROC-{p.num(5)} · Date: 2026-11-{r.randint(2, 10):02d}", "", "## Company", f"- Registered name: {S('org_name', name)}",
         f"- {S('tax_id', reg, c['reg'] + ': ' + reg)}", f"- Address: {S('company_address', addr)}", f"- Country: {c['country']} — {S('foreign', True, 'foreign supplier (no Taiwan UBN)')}",
         f"- Date of establishment: {S('established', est.isoformat(), p.dt(est))}", f"- {S('business_type', bt, 'Business type: ' + btl)}",
         f"- Services/goods: {S('services', services)}", f"- {S('service_area', area_[0], 'Geographic service area: ' + area_[1])}",
         f"- Gross annual sales: {S('gross_sales', str(sales), f'{c['cur']} {sales:,}')} (FY2025)", "", "## Point of contact",
         f"- {S('contact_name', [f'{first} {last}', f'{hon} {first} {last}'], f'{hon} {first} {last}')}, {S('contact_title', title)}",
         f"- Email: {S('email', f'{first}.{last}'.lower() + f'@{stem}.example')}", f"- Phone (day): {S('phone_day', phone)}",
         f"- Phone (evening): {S('phone_evening', phone[:-4] + p.dig(4))}" if p.chance(0.3) else "- Phone (evening): not provided by the vendor", "", "## Compliance",
         f"- {S('insurance', 'insured', 'Insurance: Insured')} — liability policy CLP-{p.dig(2)}-{p.num(5)}" if p.chance(0.8) else f"- {S('insurance', 'not_insured', 'Insurance: Not insured')}"]
    if p.chance(0.6):
        L.append(f"- {S('licensing', 'licensed', 'Licensing: Licensed')} — licence no. {S('license_number', cc + '-LIC-' + p.num(7))}")
    else:
        L.append(f"- {S('licensing', 'not_licensed', 'Licensing: Not licensed (not required)')}")
    L += ["", "## Banking", f"- Bank: {S('bank_name', bank)} (fictional)", f"- Beneficiary name: {S('beneficiary', name)}", f"- Account number: {S('account_number', acct)}",
          "- SWIFT: to be confirmed by the vendor's bank" if split == "train" and p.chance(0.07) else f"- SWIFT: {S('swift', ''.join(w[0] for w in bank.split())[:4].ljust(4, 'X').upper() + cc + r.choice('2AX') + r.choice('LSX') + 'XXX')}",
          f"- Payment terms: {S('payment_terms', *terms)} · {S('currency', c['cur'], 'Currency: ' + c['cur'])}", f"- {S('invoice_type', 'foreign_invoice', 'Invoice type: overseas commercial invoice')}"]
    of, ol, _ = p.person(False)
    L += p.notes("Unrelated in this pack", [f"Competing quote: {p.uniq(lambda: f'{r.choice(STEMS[split])} {sector} {c["suffix"]}')} — rejected on price.",
                                          "Kestrel's own billing address: 1 Science Park Rd, Singapore 117528 — not the vendor's address.",
                                          f"Internal requester: {of} {ol} (Logistics), {p.tw_mobile()} — not the vendor contact.",
                                          f"Vendor's previous bank account ending {p.dig(4)} was closed in 2025; do not use.", "On-site audit must be completed within 30 days."], 3)
    return "\n".join(L) + "\n"


ZH_SUR = [("王", "Wang"), ("張", "Chang"), ("劉", "Liu"), ("楊", "Yang"), ("吳", "Wu"), ("許", "Hsu"), ("郭", "Kuo"), ("鄭", "Cheng"), ("謝", "Hsieh"),
          ("邱", "Chiu"), ("廖", "Liao"), ("賴", "Lai"), ("周", "Chou"), ("葉", "Yeh"), ("蘇", "Su"), ("呂", "Lu"), ("江", "Chiang")]
ZH_G1 = [("志", "Chih"), ("雅", "Ya"), ("俊", "Chun"), ("美", "Mei"), ("建", "Chien"), ("淑", "Shu"), ("家", "Chia"), ("怡", "Yi"), ("宗", "Tsung"), ("佩", "Pei")]
ZH_G2 = [("偉", "wei"), ("婷", "ting"), ("宏", "hung"), ("玲", "ling"), ("華", "hua"), ("芬", "fen"), ("明", "ming"), ("君", "chun"), ("翰", "han"), ("萱", "hsuan")]
ZH_A = [("鴻", "Hong"), ("昇", "Sheng"), ("耀", "Yao"), ("祥", "Xiang"), ("嘉", "Jia"), ("順", "Shun"), ("盛", "Cheng"), ("弘", "Hung"), ("瑞", "Rui"), ("凱", "Kai"),
        ("泓", "Hon"), ("立", "Li"), ("興", "Hsing"), ("冠", "Kuan"), ("晟", "Sun")]
ZH_B = [("遠", "yuan"), ("暘", "yang"), ("群", "chun"), ("鉅", "ju"), ("展", "chan"), ("益", "yi"), ("泰", "tai"), ("碩", "shuo"), ("昌", "chang"), ("勝", "sheng"),
        ("格", "ge"), ("達", "da"), ("邁", "mai"), ("宇", "yu"), ("崧", "song")]
ZH_IND = [("精密工業", "Precision Industrial", "CNC 精密加工零件、治具製作", "CNC precision machined parts and fixtures"),
          ("科技", "Technology", "工業電腦與嵌入式控制板", "Industrial PCs and embedded control boards"),
          ("機電", "Electromechanical", "廠務機電工程與維護", "Facility electromechanical engineering and maintenance"),
          ("化工材料", "Chemical Materials", "半導體製程用特用化學品", "Specialty chemicals for semiconductor processes"),
          ("自動化設備", "Automation Equipment", "自動化搬運設備與機械手臂整合", "Automated material handling and robot integration"),
          ("電子材料", "Electronic Materials", "銅箔基板與封裝材料", "Copper-clad laminates and packaging materials"),
          ("包裝", "Packaging", "防靜電包裝材料與晶圓盒", "ESD-safe packaging and wafer carriers"),
          ("物流", "Logistics", "無塵室設備搬運與倉儲", "Cleanroom equipment moving and warehousing"),
          ("氣體", "Gases", "大宗氣體與特殊氣體供應", "Bulk and specialty gas supply"),
          ("環保科技", "Environmental Technology", "廢水處理與廢溶劑回收", "Wastewater treatment and solvent recycling")]
ZH_ADDR = [("臺北市", "Taipei City", "內湖區", "Neihu Dist.", "114", "02"), ("臺北市", "Taipei City", "南港區", "Nangang Dist.", "115", "02"),
           ("臺北市", "Taipei City", "中山區", "Zhongshan Dist.", "104", "02"), ("新北市", "New Taipei City", "汐止區", "Xizhi Dist.", "221", "02"),
           ("新北市", "New Taipei City", "新莊區", "Xinzhuang Dist.", "242", "02"), ("新北市", "New Taipei City", "中和區", "Zhonghe Dist.", "235", "02"),
           ("桃園市", "Taoyuan City", "龜山區", "Guishan Dist.", "333", "03"), ("桃園市", "Taoyuan City", "中壢區", "Zhongli Dist.", "320", "03"),
           ("桃園市", "Taoyuan City", "蘆竹區", "Luzhu Dist.", "338", "03"), ("新竹市", "Hsinchu City", "東區", "East Dist.", "300", "03"),
           ("新竹市", "Hsinchu City", "香山區", "Xiangshan Dist.", "300", "03"), ("新竹縣", "Hsinchu County", "竹北市", "Zhubei City", "302", "03"),
           ("新竹縣", "Hsinchu County", "湖口鄉", "Hukou Township", "303", "03"), ("新竹縣", "Hsinchu County", "寶山鄉", "Baoshan Township", "308", "03"),
           ("臺中市", "Taichung City", "西屯區", "Xitun Dist.", "407", "04"), ("臺中市", "Taichung City", "南屯區", "Nantun Dist.", "408", "04"),
           ("臺中市", "Taichung City", "大里區", "Dali Dist.", "412", "04"), ("臺南市", "Tainan City", "永康區", "Yongkang Dist.", "710", "06"),
           ("臺南市", "Tainan City", "善化區", "Shanhua Dist.", "741", "06"), ("高雄市", "Kaohsiung City", "前鎮區", "Qianzhen Dist.", "806", "07"),
           ("高雄市", "Kaohsiung City", "楠梓區", "Nanzi Dist.", "811", "07"), ("高雄市", "Kaohsiung City", "左營區", "Zuoying Dist.", "813", "07")]
ZH_ROADS = [("中正路", "Zhongzheng Rd."), ("中山路", "Zhongshan Rd."), ("民生路", "Minsheng Rd."), ("光復路", "Guangfu Rd."), ("文化路", "Wenhua Rd."),
            ("成功路", "Chenggong Rd."), ("建國路", "Jianguo Rd."), ("復興路", "Fuxing Rd."), ("和平路", "Heping Rd."), ("自強路", "Ziqiang Rd."),
            ("工業一路", "Gongye 1st Rd."), ("科技路", "Keji Rd.")]
TW_BANKS = [("004", "臺灣銀行", "Bank of Taiwan"), ("005", "臺灣土地銀行", "Land Bank of Taiwan"), ("006", "合作金庫商業銀行", "Taiwan Cooperative Bank"),
            ("007", "第一商業銀行", "First Commercial Bank"), ("008", "華南商業銀行", "Hua Nan Commercial Bank"), ("009", "彰化商業銀行", "Chang Hwa Commercial Bank"),
            ("012", "台北富邦商業銀行", "Taipei Fubon Commercial Bank"), ("013", "國泰世華商業銀行", "Cathay United Bank"), ("017", "兆豐國際商業銀行", "Mega International Commercial Bank"),
            ("808", "玉山商業銀行", "E.SUN Commercial Bank"), ("812", "台新國際商業銀行", "Taishin International Bank"), ("822", "中國信託商業銀行", "CTBC Bank")]
ZH_TITLES = [("業務經理", "Sales Manager"), ("業務專員", "Sales Representative"), ("財務主任", "Finance Supervisor"), ("總經理特助", "Assistant to the General Manager"), ("專案經理", "Project Manager")]
ZH_TERMS = [("net30", "月結 30 天"), ("net45", "月結 45 天"), ("net60", "月結 60 天"), ("net90", "月結 90 天"), ("cod", "貨到付款")]
UBN_W = [1, 2, 1, 2, 1, 2, 4, 1]


def ubn(p):
    while True:
        s = p.r.choice("1234" if p.split == "train" else "6789") + p.dig(7)
        if s[6] != "7" and sum(sum(divmod(w * int(c), 10)) for w, c in zip(UBN_W, s)) % 5 == 0 and s not in p.run.used:
            p.run.used.add(s)
            p.ident.append(s)
            return s


def zh_person(p):
    def make():
        s, a, b = p.r.choice(ZH_SUR), p.r.choice(ZH_G1), p.r.choice(ZH_G2)
        return f"{s[0]}{a[0]}{b[0]}|{s[1]} {a[1]}-{b[1]}"
    return p.uniq(make).split("|")


def gen_vendor_tw(p, family):
    r, S = p.r, p.S

    def co():
        a, b, ind = r.choice(ZH_A), r.choice(ZH_B), r.choice(ZH_IND)
        return f"{a[0]}{b[0]}|{a[1]}{b[1]}|{ZH_IND.index(ind)}"
    stem_zh, stem_en, ii = p.uniq(co).split("|")
    ind = ZH_IND[int(ii)]
    corp = p.chance(0.7)
    zh = f"{stem_zh}{ind[0]}{'股份有限公司' if corp else '有限公司'}"
    en = f"{stem_en} {ind[1]} Co., Ltd."
    p.ident += [zh, en]
    county, county_en, dist, dist_en, postal, area = r.choice(ZH_ADDR)
    road, road_en = r.choice(ZH_ROADS)
    no, fl = r.randint(1, 380), r.randint(2, 12)
    dc = county.replace("臺", "台") if p.chance(0.5) else county
    line = f"{road}{no}號{fl}樓"
    zh_addr, en_addr = f"{postal} {dc}{dist}{line}", f"{fl}F., No. {no}, {road_en}, {dist_en}, {county_en} {postal}"
    tel = f"{area}-{p.dig(4)}-{p.dig(4)}" if area == "02" else f"{area}-{p.dig(3)}-{p.dig(4)}"
    owner, _ = zh_person(p)
    cname, cname_en = zh_person(p)
    title = r.choice(ZH_TITLES)
    est = p.day(date(1978, 1, 1), date(2021, 12, 31))
    cap = r.randint(5, 900) * 1000000
    bank = r.choice(TW_BANKS)
    obank = r.choice([b for b in TW_BANKS if b != bank])
    branch = dist[:-1] + "分行"
    acct = p.num(r.choice([12, 13, 14]))
    terms, cur = r.choice(ZH_TERMS), (("TWD", "新台幣 TWD") if p.chance(0.85) else ("USD", "美元 USD"))
    inv = r.choice([("egui3", "電子發票（三聯式）"), ("egui3", "電子發票（三聯式）"), ("egui2", "電子發票（二聯式）"), ("receipt", "收據")])
    sales = r.randint(12, 980) * 1000000
    no_ = ubn(p)
    S("tax_id", no_, no_)
    S("org_name", [en, zh], en)
    S("company_address", [zh_addr, en_addr], zh_addr)
    S("county", county, dc + dist)
    S("district", dist, dc + dist)
    S("address_line", line)
    S("postal", postal, postal + " " + dc)
    S("phone_day", tel, tel)
    S("account_number", acct, acct)
    S("beneficiary", [zh, en], "戶名：" + zh)
    S("business_type", "corporation" if corp else ["llc", "private_limited"], "股份有限公司" if corp else "有限公司")
    rows = [("公司名稱（中文）", S("vendor_name_zh", zh)), ("公司名稱（英文）", S("vendor_name_en", en)), ("廠商類別", S("foreign", False, "國內廠商")), ("統一編號", S("ubn", no_)),
            ("負責人", S("owner", owner)), ("設立日期", S("established", est.isoformat(), f"民國{est.year - 1911}年{est.month}月{est.day}日（{est.isoformat()}）")),
            ("資本額", S("capital", str(cap), f"NT${cap:,}") if p.chance(0.85) else "未提供"), ("組織型態", S("org_type", "corp_shares" if corp else "limited", "股份有限公司" if corp else "有限公司")),
            ("營業項目", S("services", [ind[2], ind[3]], ind[2])), ("公司地址", zh_addr), ("公司電話", S("tel", tel)), ("傳真", S("fax", tel[:-4] + p.dig(4)) if p.chance(0.7) else "無")]
    L = ["# 供應商主檔資料表（採購部 內部文件）", f"機密等級：限閱｜文件編號 PUR-VM-2026-{p.num(4)}｜日期：2026-11-{r.randint(2, 10):02d}", "（本文件之公司與人員皆為虛構，供表單訓練使用）", "",
         "## 一、基本資料", "| 欄位 | 內容 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]
    L += ["", "## 二、聯絡窗口", f"- 業務聯絡人：{S('contact_name', [cname, cname_en], cname)}（{S('contact_title', [title[0], title[1]], title[0])}）",
          "- 電子郵件：未提供（僅以電話聯絡）" if p.chance(MISS) else f"- 電子郵件：{S('email', cname_en.split(' ')[1].lower().replace('-', '') + '.' + cname_en.split(' ')[0].lower() + '@' + stem_en.lower() + '-' + ind[1].split(' ')[0].lower() + '.example')}",
          f"- 手機：{S('contact_mobile', p.tw_mobile(False))}" if p.chance(0.94) else "- 手機：未提供", "- 晚間聯絡電話：未提供", "", "## 三、付款與發票",
          f"- 匯款銀行：{S('bank_name', [bank[1], bank[2]], bank[1])}（{S('bank_code', bank[0], '銀行代碼 ' + bank[0])}）{S('bank_branch', [branch, branch[:-2]], branch)}",
          f"- 帳號：{S('account_no', acct)}", f"- 戶名：{S('account_name', zh)}", f"- 付款條件：{S('payment_terms', *terms)}", f"- 發票類型：{S('invoice_type', *inv)}",
          f"- 幣別：{S('currency', *cur)}", "", "## 四、認證與其他"]
    if p.chance(0.6):
        exp = p.day(date(2027, 1, 1), date(2029, 12, 31))
        L.append(f"- {S('iso9001', True, 'ISO 9001：有')}，證書到期日 {S('iso_expiry', exp.isoformat())}")
    else:
        L.append(f"- {S('iso9001', False, 'ISO 9001：無')}")
    ins = p.chance(0.75)
    L += [f"- {S('insurance', 'insured' if ins else 'not_insured', '產品責任保險：有投保' if ins else '產品責任保險：未投保')}",
          f"- 年營業額：{S('gross_sales', str(sales), f'約 NT${sales:,}')}（2025 年度）"]
    L += ["", "## 附註（與本次建檔無關）"] + [f"- {x}" for x in r.sample([
        f"比價廠商：{p.uniq(lambda: r.choice(ZH_A)[0] + r.choice(ZH_B)[0])}{ind[0]}有限公司（統一編號 {ubn(p)}）報價較高，未採用。",
        f"舊匯款帳號 {obank[1]} {p.dig(4)}-{p.dig(3)}-{p.num(6)} 已於 2025 年結清，請勿使用。", "內部稽核提醒：新供應商須於 30 天內完成實地評鑑。",
        f"11/{r.randint(12, 28)} 下午 採購部 季會，地點 3 樓會議室。", f"前任聯絡人 {zh_person(p)[0]} 已離職。"], 3)]
    return "\n".join(L) + "\n"


# ================================================================ Japanese trip request (jp-travel-request)
JP_SUR = [("田中", "tanaka"), ("高橋", "takahashi"), ("渡辺", "watanabe"), ("伊藤", "ito"), ("中村", "nakamura"), ("小林", "kobayashi"), ("加藤", "kato"),
          ("吉田", "yoshida"), ("山口", "yamaguchi"), ("松本", "matsumoto"), ("井上", "inoue"), ("清水", "shimizu"), ("斎藤", "saito"), ("森", "mori"),
          ("池田", "ikeda"), ("橋本", "hashimoto"), ("前田", "maeda"), ("岡田", "okada")]
JP_GIV = [("大輔", "daisuke"), ("翔太", "shota"), ("拓海", "takumi"), ("直樹", "naoki"), ("健太", "kenta"), ("陽子", "yoko"), ("恵", "megumi"), ("由香", "yuka"),
          ("彩", "aya"), ("智子", "tomoko"), ("裕介", "yusuke"), ("亮", "ryo"), ("剛", "tsuyoshi"), ("誠", "makoto"), ("麻衣", "mai"), ("千尋", "chihiro")]
JP_DEST = [("TW", "台湾", "新竹市", "新竹工場", "新竹サイエンスパーク・レジデンス", "TWD", "BR"), ("TW", "台湾", "台北市", "台北本社", "内湖リバーサイドホテル", "TWD", "CI"),
           ("TW", "台湾", "台南市", "台南アセンブリ工場", "台南パークサイドホテル", "TWD", "JL"), ("SG", "シンガポール", "シンガポール", "シンガポール地域統括オフィス", "マリーナ・ベイサイド・イン", "SGD", "SQ"),
           ("US", "アメリカ合衆国", "サンノゼ", "米国設計センター", "ノースファースト・ホテル", "USD", "NH"), ("US", "アメリカ合衆国", "オースティン", "オースティン営業所", "レイクビュー・イン", "USD", "UA"),
           ("KR", "韓国", "水原", "協力会社 水原工場", "水原セントラルホテル", "USD", "KE"), ("DE", "ドイツ", "ドレスデン", "装置メーカー本社", "エルベ河畔ホテル", "USD", "LH"),
           ("VN", "ベトナム", "ホーチミン", "委託組立工場", "サイゴン・リバーホテル", "USD", "VN"), ("MY", "マレーシア", "ペナン", "ペナン工場", "ベイビュー・ホテル", "USD", "MH"),
           ("CN", "中国", "蘇州", "協力会社 蘇州工場", "金鶏湖ホテル", "USD", "NH")]
JP_PURPOSE = ["歩留まり改善会議への出席および工程監査", "新規装置の立上げ支援", "品質監査および是正処置の確認", "量産移管に関する技術打合せ", "サプライヤー定期監査", "設備据付の立会いと検収"]
JP_TITLES = ["主任", "係長", "課長代理", "担当", "主査"]


def jp_person(p):
    def make():
        s, g = p.r.choice(JP_SUR), p.r.choice(JP_GIV)
        return f"{s[0]} {g[0]}|{g[1][0]}.{s[1]}"
    return p.uniq(make).split("|")


def gen_trip(p, family):
    r, S = p.r, p.S
    name, local = jp_person(p)
    dept = r.choice(JP_DEPTS)
    appr = r.choice(p.run.jp_managers)
    cc, country, city, site, hotel, hcur, al = r.choice(JP_DEST)
    d1 = p.day(date(2026, 12, 1), date(2027, 3, 20))
    nights = r.randint(2, 6)
    d2 = d1 + timedelta(days=nights)
    air, rate, local_amt, adv = r.randint(450, 2400) * 100, r.randint(20, 90) * (100 if hcur == "TWD" else 5), r.randint(10, 80) * (100 if hcur == "TWD" else 5), r.randint(3, 15) * 10000
    f1, f2 = f"{al} {r.randint(100, 899)}", f"{al} {r.randint(100, 899)}"
    visa = cc in ("CN", "VN") and p.chance(0.7)

    def jd(d):
        return f"{d.year}年{d.month}月{d.day}日"
    L = ["# 海外出張計画書（社内資料）", f"ケストレル・セミコンダクター株式会社 {dept[1].split(' ')[0]} ／ 社外秘 ／ 作成日 2026-11-{r.randint(2, 10):02d}", "※本資料の人物・組織は架空です（学習用データ）。", "",
         "## 申請者", f"- 氏名：{S('name', [name, name.replace(' ', '')], name)}", f"- 社員番号：{S('emp_no', 'J-' + p.num(5))}", f"- 所属：{S('dept', *dept)}",
         f"- 役職：{S('title', r.choice(JP_TITLES))}", f"- 原価センター：{S('cost_center', r.choice(JP_CC[dept[0]]))}", f"- 社用メール：{S('email', local + '@kestrel-semi.example')}",
         f"- 携帯電話：{S('mobile', r.choice(['080', '090', '070']) + '-' + p.dig(4) + '-' + p.dig(4))}", f"- 承認者：{S('approver', appr[0], appr[1])}（{appr[2]}）", "", "## 出張内容",
         f"- 出張先：{S('dest_country', cc, country + ' ' + city)}（{site}）", f"- 目的：{S('purpose', site + ' ' + r.choice(JP_PURPOSE))}",
         f"- 期間：{S('depart_date', d1.isoformat(), jd(d1))} 〜 {S('return_date', d2.isoformat(), jd(d2))}（{nights}泊{nights + 1}日）"]
    S("dest_city", [city, city[:-1]] if city.endswith("市") else city, city)
    if p.chance(0.8):
        L += [f"- 往路：{d1.month}月{d1.day}日 {S('outbound_flight', f1)}", f"- 復路：{d2.month}月{d2.day}日 {S('return_flight', f2)}"]
    else:
        L.append("- 航空便：総務部で手配中（便名未定）")
    L.append(f"- 宿泊先：{S('hotel', hotel)}（1泊 {hcur} {rate:,} × {nights}泊）" if p.chance(0.85) else "- 宿泊先：現地法人が手配（未定）")
    L.append(f"- {S('visa_needed', 'yes', 'ビザ：必要')}（商用ビザ申請中）" if visa else f"- {S('visa_needed', 'no', 'ビザ：不要')}（短期商用・査証免除）")
    rows = [f"| 航空券（往復） | {S('exp_air_amount', str(air), f'{air:,}')} | JPY |", f"| 宿泊費 | {S('exp_hotel_amount', str(rate * nights), f'{rate * nights:,}')} | {hcur} |"]
    S("exp_air_cur", "JPY", rows[0])
    S("exp_hotel_cur", hcur, rows[1])
    if p.chance(0.75):
        rows.append(f"| 現地交通費 | {S('exp_local_amount', str(local_amt), f'{local_amt:,}')} | {hcur} |")
        S("exp_local_cur", hcur, rows[2])
    L += ["", "## 費用見積", "| 項目 | 金額 | 通貨 |", "|---|---|---|"] + rows + [f"- 仮払金の希望額：{S('advance_amount', str(adv), f'{adv:,}円')}（円建て、出発前に口座振込）"]
    S("advance_cur", "JPY", f"{adv:,}円（円建て")
    exp = p.day(date(2027, 6, 1), date(2035, 12, 31))
    L += ["", "## パスポート", "- 旅券：更新手続き中（新しい旅券番号は未確定）" if p.chance(MISS + 0.01) else
          f"- 旅券番号：{S('passport_no', r.choice('TMZK') + r.choice('RKSH') + p.num(7))} ／ 有効期限：{S('passport_expiry', exp.isoformat())}"]
    other, _ = jp_person(p)
    L += ["", "## 部内連絡（本申請とは無関係）"] + [f"- {x}" for x in r.sample([
        f"前回出張（2026年{r.randint(5, 10)}月 {r.choice(JP_DEST)[2]}）の精算は完了済み。", f"{other}（J-{p.num(5)}）も同時期に出張予定だが、別申請。",
        "12月第2週の部内定例はオンライン開催。", "年末調整書類の提出期限は11月20日。", f"前回の仮払金 {r.randint(3, 9)}0,000円 は返金済み。"], 3)]
    return "\n".join(L) + "\n"


# ================================================================ US tax portal (eval-only family)
BT_US = [("llc", "Limited Liability Company", "LLC"), ("corporation", "Corporation", "Inc."), ("s_corp", "S Corporation", "Inc."), ("partnership", "Partnership", "LLP"),
         ("sole_prop", "Sole Proprietor", "Studio"), ("nonprofit", "Non-profit", "Foundation")]


def gen_ustax(p, family):
    r, S, split = p.r, p.S, p.split
    bt = r.choice(BT_US)
    legal = p.uniq(lambda: f"{r.choice(STEMS[split])} {r.choice(['Analytics', 'Logistics', 'Design', 'Consulting', 'Bioscience', 'Robotics'])} {bt[2]}")
    first, last, _ = p.person(False)
    mi = r.choice("ABCDEJKLMRST") if p.chance(0.6) else ""
    suffix = r.choice(["Jr.", "III"]) if p.chance(0.15) else ""
    street, city, st, _, zp, area = p.us_addr(DE_CITIES)
    ostreet, ocity, ost, _, ozp, _ = p.us_addr(DE_CITIES)
    suite = f"Suite {r.randint(100, 900)}" if p.chance(0.6) else ""
    est = p.day(date(2005, 1, 1), date(2024, 12, 31))
    email = f"{first[0]}{last}".lower() + "@" + legal.split(" ")[0].lower() + ".example"
    pos = r.choice(["Controller", "Chief Financial Officer", "Office Manager", "Tax Manager", "Owner", "Bookkeeper"])
    sig = f"{first} {mi + '. ' if mi else ''}{last}{' ' + suffix if suffix else ''}"
    S("email_confirm", email, email)
    S("legal_name", legal)
    S("urbanization", "", f"{city}, {st} {zp}")
    L = [f"# {legal} — Entity Fact Sheet", "Finance Operations · CONFIDENTIAL · Fictional company for training", "", "## Entity", f"- Legal name: {S('org_name', legal)}",
         f"- Business type: {S('business_type', bt[0], bt[1])}", f"- FEIN: {S('fein', p.dig(2) + '-' + p.num(7))}", f"- Date established: {S('established', est.isoformat(), p.dt(est))}",
         f"- Principal address: {S('street1', street)}, " + (f"{S('street2', suite)}, " if suite else "") + f"{S('city', city)}, {S('state', st, f'{st} {zp}')[:2]} {S('zip', zp)}",
         f"- State portal PIN (from the Division of Revenue letter): {S('portal_pin', p.num(7))}" if p.chance(0.88) else "- State portal PIN letter received: yes (PIN kept in the Finance safe — not copied here)",
         "", "## Portal / registration contact",
         f"- {sig} — {S('position', pos)} (first name {S('first_name', first)}, " + (f"middle initial {S('middle_initial', mi)}" if mi else S("middle_initial", "", "no middle initial"))
         + f", last name {S('last_name', last)}, " + (f"suffix {S('suffix', suffix)}" if suffix else S("suffix", "", "no suffix")) + f", {S('preferred_name', first, 'goes by ' + first)})",
         f"- Email: {S('email', email)}", f"- Day phone: {S('day_phone', p.us_phone(area))} · Mobile: {S('mobile_phone', p.us_phone(area))} ({S('country_code', '1', 'country code +1')} for both)",
         f"- Preferred portal user ID: {S('user_id', legal.split(' ')[0].lower() + '.' + first[0].lower() + last.lower())}",
         f"- {first} {S('accept_terms', True, 'approved accepting the portal usage terms')} and {S('certify', True, 'attests the information is accurate')} (electronic signature: {S('esign', sig)})"]
    S("mobile_country_code", "1", "country code +1")
    L += p.notes("Unrelated", [f"Sister entity {legal.split(' ')[0]} Holdings {r.choice(['Inc.', 'LP'])} (FEIN {p.dig(2)}-{p.num(7)}) — different company.",
                              f"Former office: {ostreet}, {ocity}, {ost} {ozp} (closed {r.randint(2019, 2025)}).", "Auditor engagement letter due 2027-01-15.",
                              "Sales tax filing is handled by an outside preparer.", f"Previous portal contact left the company in {r.randint(2022, 2025)}."], 3)
    return "\n".join(L) + "\n"


# ================================================================ Taiwan arrival card (eval-only family)
TRAV = {"PH": ("Philippines", ["BAUTISTA", "VILLANUEVA", "MENDOZA", "AQUINO", "NAVARRO"], ["ANGELA MARIE", "JOSE MIGUEL", "PATRICIA ANNE", "CARLO", "LIZA"], "PR", "Manila"),
        "JP": ("Japan", ["OGAWA", "FUJITA", "ISHIKAWA", "NOMURA", "SAKAI"], ["HARUKA", "DAICHI", "YUI", "SOTA", "MIO"], "JL", "Tokyo"),
        "SG": ("Singapore", ["LIM", "ONG", "GOH", "TEO", "CHUA"], ["WEI JIE", "XIN YI", "JIA HUI", "KAI WEN", "ZHI HAO"], "SQ", "Singapore"),
        "US": ("United States", ["MILLER", "ANDERSON", "BROOKS", "HAYES", "WHITAKER"], ["EMILY", "JACOB", "OLIVIA", "NATHAN", "AVERY"], "UA", "San Francisco"),
        "MY": ("Malaysia", ["ISMAIL", "RAZAK", "YUSOF", "HAMID", "OTHMAN"], ["NURUL AIN", "AMIRUL", "SITI", "HAFIZ", "FARAH"], "MH", "Kuala Lumpur"),
        "HK": ("Hong Kong", ["CHEUNG", "LAU", "YIP", "KWOK", "TSANG"], ["KA MAN", "TSZ HIN", "WING YAN", "CHUN KIT", "HOI LAM"], "CX", "Hong Kong")}
TW_STAY = [("Hsinchu City", "新竹市", "East Dist.", "東區", "300"), ("Taipei City", "臺北市", "Neihu Dist.", "內湖區", "114"), ("Taipei City", "臺北市", "Da'an Dist.", "大安區", "106"),
           ("Taipei City", "臺北市", "Xinyi Dist.", "信義區", "110"), ("Taipei City", "臺北市", "Zhongshan Dist.", "中山區", "104"), ("New Taipei City", "新北市", "Banqiao Dist.", "板橋區", "220"),
           ("Taoyuan City", "桃園市", "Zhongli Dist.", "中壢區", "320"), ("Taoyuan City", "桃園市", "Dayuan Dist.", "大園區", "337"), ("Taichung City", "臺中市", "Xitun Dist.", "西屯區", "407"),
           ("Tainan City", "臺南市", "Shanhua Dist.", "善化區", "741"), ("Kaohsiung City", "高雄市", "Zuoying Dist.", "左營區", "813"), ("Hsinchu County", "新竹縣", "Zhubei City", "竹北市", "302")]
OCCS = [("engineer", ["Senior Quality Engineer", "Process Engineer", "Field Service Engineer"]), ("business", ["Sales Director", "Account Manager", "Procurement Lead"]),
        ("student", ["Graduate student (exchange program)"]), ("other", ["Corporate chef", "Occupational nurse", "Interpreter"])]
PURP = [("business", "Business"), ("business", "Business"), ("employment", "Employment"), ("conference", "Conference"), ("study", "Study"), ("visit_relatives", "Visiting relatives")]
VISAS = [("visitor", "Visitor Visa"), ("resident", "Resident Visa"), ("landing", "Landing Visa"), ("evisa", "eVisa")]


def gen_arrival(p, family):
    r, S = p.r, p.S
    cc = r.choice(list(TRAV))
    country, surs, givs, al, origin = TRAV[cc]
    fam, giv = p.uniq(lambda: f"{r.choice(surs)}|{r.choice(givs)}").split("|")
    sex = r.choice(["Female", "Male"])
    dob = p.day(date(1962, 1, 1), date(2003, 12, 31))
    pexp = p.day(date(2027, 8, 1), date(2035, 12, 31))
    occ = r.choice(OCCS)
    arr = p.day(date(2026, 11, 20), date(2027, 2, 27))
    purpose = r.choice(PURP)
    city, county, dist_en, dist, postal = r.choice(TW_STAY)
    stay = r.choice([("hotel", f"{dist_en.split(' ')[0]} Garden Hotel"), ("residence", "company residence"), ("relatives", "relative's home")])
    addr = f"No. {r.randint(1, 320)}, {r.choice(EN_ROADS)} Rd., {dist_en}, {city} {postal}"
    others = [c for c in ("PH", "JP", "SG", "HK", "US", "MY") if c != cc]
    extra = r.choice(others) if p.chance(0.35) else None
    visited = sorted([cc] + ([extra] if extra else []))
    L = [f"# Global Mobility — Arrival Dossier: {giv.title()} {fam.title()}", "Kestrel Semiconductor Taiwan Ltd. · HR Global Mobility · CONFIDENTIAL · Fictional training data",
         f"Case GM-2026-{p.num(4)}", "", "## Traveller", f"- Name as in passport: {fam}, {giv} (family name {S('family_name', fam)}, given names {S('given_name', giv)})",
         f"- {S('sex', sex.lower(), 'Sex: ' + sex)} · Date of birth: {S('dob', dob.isoformat(), p.dt(dob))}", f"- {S('nationality', cc, 'Nationality: ' + country)}",
         f"- Passport no.: {S('passport_no', r.choice('PEKM') + p.num(7) + r.choice('ABX'))} · Expires {S('passport_expiry', pexp.isoformat(), p.dt(pexp))}",
         f"- Occupation: {S('occupation', occ[0], r.choice(occ[1]))}", "", "## Entry to Taiwan",
         f"- Arrival date: {S('arrival_date', arr.isoformat(), p.dt(arr))} · Flight {S('flight_no', f'{al} {r.randint(100, 899)}')} ({origin} → Taoyuan)",
         f"- Departure flight: {S('departure_flight', f'{al} {r.randint(100, 899)}')}" if p.chance(0.5) else f"- {S('departure_flight', '', 'Departure: open — leave the departure flight blank')}",
         f"- {S('purpose', purpose[0], 'Purpose of visit: ' + purpose[1])}"]
    if p.chance(0.08):
        L.append(f"- {S('visa_type', 'visa_exempt', 'Visa: visa-exempt entry')} — there is no visa or entry permit number")
    else:
        v = r.choice(VISAS)
        L.append(f"- {S('visa_type', v[0], 'Visa type: ' + v[1])} · Visa no. {S('visa_no', 'V-' + p.num(7))}")
    L += [f"- Staying at: {S('stay_type', stay[0], stay[1])} — {S('stay_address', [addr, stay[1] + ', ' + addr], addr)}", f"- Taiwan phone (company SIM): {S('phone', p.tw_mobile())}",
          f"- Email: {S('email', (giv.split(' ')[0] + '.' + fam).lower() + '@kestrel-semi.example')}" if p.chance(0.8) else "- Email: none on file",
          f"- {S('visited', visited, 'Countries visited in the last 14 days: ' + country + (' and ' + TRAV[extra][0] if extra else ' only'))}",
          f"- The traveller {S('declare', True, 'confirmed that all details above are true and correct')} (call of 2026-11-{r.randint(2, 10):02d})."]
    S("county", county, f"{dist_en}, {city}")
    S("district", dist, f"{dist_en}, {city}")
    L += p.notes("Not for the arrival card", [f"Colleague {r.choice(givs).title()} {fam.title()} travels separately — a different person.", f"Moving company quote MV-{p.dig(4)} pending approval.",
                                             f"Previous assignment: {r.choice(['Penang', 'Singapore', 'Austin', 'Dresden'])}, 2022–2026.", "Dependents: none.",
                                             f"Old passport (cancelled): {r.choice('PEKM')}{p.dig(7)}."], 3)
    return "\n".join(L) + "\n"


# ================================================================ plan
GEN = {"itsm-request": [(gen_employee, "emp", N_TRAIN)], "hr-orangehrm": [(gen_employee, "emp", N_TRAIN)], "event-registration": [(gen_employee, "emp", N_TRAIN)],
       "emr-registration": [(gen_patient, "patient", N_TRAIN)], "parabank": [(gen_bank, "customer", N_TRAIN)], "kyc-account-opening": [(gen_kyc, "kyc", N_TRAIN)],
       "vendor-onboarding": [(gen_vendor_intl, "intl", N_TRAIN), (gen_vendor_tw, "tw", 12)], "tw-vendor-master": [(gen_vendor_tw, "tw", N_TRAIN), (gen_vendor_intl, "intl", 8)],
       "jp-travel-request": [(gen_trip, "trip", N_TRAIN)], "us-tax-portal": [(gen_ustax, "entity", 0)], "tw-arrival-card": [(gen_arrival, "traveller", 0)]}


def generate(seed=1):
    """-> (personas, run). Deterministic for a given seed."""
    run, out = Run(), []
    for split in ("train", "eval"):
        p = P(run, random.Random(f"{seed}/managers/{split}"), split)
        for _ in range(10):
            first, last, _tw = p.person()
            uid = "u_m" + p.num(4)
            dept = p.r.choice(DEPTS)[1]
            run.managers[split].append((uid, f"{first} {last}", f"{p.r.choice(['Manager', 'Director', 'Section Manager', 'Head'])}, {dept}"))
            run.users[split].append((uid, f"{first} {last}", f"{first}.{last}".lower().replace("-", "") + f"@ · {dept} (manager)"))
    p = P(run, random.Random(f"{seed}/jp-managers"), "train")
    for i in range(12):
        name, _ = jp_person(p)
        run.jp_managers.append(("u_j" + p.num(4), name, f"{p.r.choice(JP_DEPTS)[1].split(' ')[0]} {p.r.choice(['部長', '課長', '次長'])}"))
        run.jp_users["train"].append(run.jp_managers[-1])
        if i % 2 == 0:                                   # near-duplicate: same surname, different given name
            twin = p.uniq(lambda: f"{name.split(' ')[0]} {p.r.choice(JP_GIV)[0]}")
            run.jp_users["train"].append(("u_j" + p.num(4), twin, p.r.choice(JP_DEPTS)[1]))
    for family, parts in GEN.items():
        for fn, kind, n in parts:
            for i in range(1, n + 1):
                p = P(run, random.Random(f"{seed}/{family}/train/{kind}/{i}"), "train")
                out.append(dict(id=f"{family}/t-{kind}-{i:03d}", family=family, split="train", variant=None, kind=kind, md=fn(p, family), facts=p.f, ident=p.ident))
        fn, kind, _ = parts[0]
        for variant in EVAL_VARIANTS.get(family, []):
            for i in range(1, N_EVAL + 1):
                p = P(run, random.Random(f"{seed}/{family}/eval/{variant}/{i}"), "eval")
                out.append(dict(id=f"{family}/e-{variant}-{i:02d}", family=family, split="eval", variant=variant, kind=kind, md=fn(p, family), facts=p.f, ident=p.ident))
    return out, run
