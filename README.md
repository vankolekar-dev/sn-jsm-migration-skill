# 🔄 ServiceNow → JSM Migration Skill

A **Rovo Dev / Rovo CLI skill** for Atlassian PS Consultants to migrate ServiceNow workflows, automations, and request types to Jira Service Management (JSM).

---

## ✨ What It Does

| Step | What Rovo Dev Does | Method |
|------|-------------------|--------|
| 1️⃣ **Parse** | Reads ServiceNow XML export (Flow Designer, Update Set, Catalog) | Automatic |
| 2️⃣ **Analyze** | Extracts workflows, automations, request types, custom fields | Automatic |
| 3️⃣ **Guide** | Generates step-by-step workflow creation guide for Jira UI | Script output |
| 4️⃣ **Create** | Creates request types and custom fields via JSM API | Automatic (API) |
| 5️⃣ **Generate** | Produces automation import JSON for Jira UI import | Automatic |

---

## 👩‍💻 How Any PS Consultant Installs It

### Prerequisites
Before installing, ensure you have:
- **Python 3.8+** — [Download](https://python.org/downloads)
- **Git** — [Download](https://git-scm.com/downloads)
- **Rovo CLI (`acli`)** — [Install guide](https://developer.atlassian.com/cloud/rovo/rovo-cli/) **OR** RoHub desktop app (internal)
- **JSM Admin API token** for the target customer instance ([Create token](https://id.atlassian.com/manage-profile/security/api-tokens))

---

### Option A — One-Command Install (Recommended)

Open Terminal and run:

```bash
curl -sSL https://raw.githubusercontent.com/vankolekar-dev/sn-jsm-migration-skill/main/install.sh | bash
```

This will:
1. ✅ Create `~/.rovodev/skills/jsm-workflow-builder/` directory
2. ✅ Download all scripts, references, and assets
3. ✅ Make scripts executable
4. ✅ Install Python dependencies (`requests`)
5. ✅ Verify the installation works

**Expected output:**
```
🔄 ServiceNow → JSM Migration Skill Installer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Python 3 found: Python 3.12.0
📁 Creating skill directory...
⬇️  Downloading skill files...
  ✅ SKILL.md
  ✅ scripts/sn_to_jsm.py
  ✅ scripts/sn_xml_parser.py
  ✅ scripts/jsm_creator.py
  ... (all files)
📦 Installing Python dependencies...
  ✅ requests
🔍 Verifying installation...
✅ Skill installed successfully!

🎉 Installation complete!
```

---

### Option B — Manual Install (Git Clone)

```bash
# Clone the repo
git clone https://github.com/vankolekar-dev/sn-jsm-migration-skill.git

# Copy skill to Rovo Dev skills directory
mkdir -p ~/.rovodev/skills/jsm-workflow-builder
cp -r sn-jsm-migration-skill/* ~/.rovodev/skills/jsm-workflow-builder/

# Make scripts executable
chmod +x ~/.rovodev/skills/jsm-workflow-builder/scripts/*.py

# Install dependencies
pip3 install requests

# Verify
python3 ~/.rovodev/skills/jsm-workflow-builder/scripts/sn_to_jsm.py --help
```

---

### Option C — RoHub (Internal Atlassian Only)

If you are using the internal **RoHub** desktop app:

1. Open RoHub → **Skills** tab
2. Click **"+"** → **Add from GitHub**
3. Enter: `https://github.com/vankolekar-dev/sn-jsm-migration-skill`
4. Click **Install**
5. Restart your RoHub session — the skill loads automatically

---

### After Installation — Verify It Works

```bash
# Check the skill is installed
ls ~/.rovodev/skills/jsm-workflow-builder/scripts/

# Run a quick help check
python3 ~/.rovodev/skills/jsm-workflow-builder/scripts/sn_to_jsm.py --help

# Test with a ServiceNow XML file (analyze only, no API calls)
python3 ~/.rovodev/skills/jsm-workflow-builder/scripts/sn_to_jsm.py \
  --input /path/to/your/servicenow_export.xml \
  --analyze-only
```

---

### Keeping the Skill Updated

To get the latest version:

```bash
# Re-run the installer (safe to run multiple times)
curl -sSL https://raw.githubusercontent.com/vankolekar-dev/sn-jsm-migration-skill/main/install.sh | bash
```

Or if you used git clone:

```bash
cd sn-jsm-migration-skill
git pull
cp -r * ~/.rovodev/skills/jsm-workflow-builder/
```

---

## 🎯 Using the Skill

### Via Rovo Dev / Rovo CLI (Conversational)

Once installed, just tell Rovo Dev:

```
"I have a ServiceNow XML export at /path/to/export.xml.
 Migrate it to JSM project ITO on https://customer.atlassian.net"
```

Rovo Dev will automatically use the skill scripts to:
- Parse the XML
- Show you an analysis report
- Generate the workflow UI guide
- Wait for your confirmation that the workflow is set up
- Create request types and fields via API

### Via Script (Direct / Scripted Runs)

```bash
# Full interactive migration
python3 ~/.rovodev/skills/jsm-workflow-builder/scripts/sn_to_jsm.py \
  --input export.xml \
  --site https://customer.atlassian-us-gov-mod.net \
  --email admin@customer.gov \
  --token YOUR_API_TOKEN \
  --project IT

# Analyze only — no API calls, just show what would be created
python3 ~/.rovodev/skills/jsm-workflow-builder/scripts/sn_to_jsm.py \
  --input export.xml \
  --analyze-only

# Generate workflow guide only (markdown file)
python3 ~/.rovodev/skills/jsm-workflow-builder/scripts/sn_to_jsm.py \
  --input export.xml \
  --workflow-guide /tmp/workflow_guide.md

# Dry run — show all planned API calls without executing
python3 ~/.rovodev/skills/jsm-workflow-builder/scripts/sn_to_jsm.py \
  --input export.xml --site ... --token ... \
  --dry-run

# Skip workflow confirmation (for scripted/CI use)
python3 ~/.rovodev/skills/jsm-workflow-builder/scripts/sn_to_jsm.py \
  --input export.xml --site ... --token ... \
  --skip-workflow-check
```

---

## 🔎 Production Live Discovery

For approved customer environments, `scripts/sn_live_assessor.py` supports a read-only ServiceNow assessment. Use Keychain-backed Basic authentication for local testing, or OAuth client credentials where customer policy permits.

- `--deep-discovery` performs complete pagination for CMDB CIs and relationships.
- `--include-script-source` performs in-memory static analysis of business and client scripts; reports retain only fingerprints and derived indicators, never source text.
- Deep discovery fails fast on API errors to prevent incomplete CMDB counts from being reported as exact.

## ⚠️ Known API Limitations (Jira Cloud)

| Capability | Via API | Via UI | Notes |
|-----------|---------|--------|-------|
| Request types | ✅ Automatic | — | Fully automated |
| Custom fields | ✅ Automatic | — | Fully automated |
| Workflow statuses/transitions | ❌ Not supported | ✅ Guide generated | Script outputs precise UI steps |
| Automation rules | ❌ Browser auth only | ✅ JSON generated | Script outputs import-ready JSON |

> **Why can't workflows be created via API?**
> Jira Cloud REST API does not support programmatic workflow creation (as of build 100292, July 2026). The `POST /rest/api/3/workflows` endpoint requires UUID-based status references that are not available via the public API on current builds. The script generates a precise, click-by-click UI guide instead.

---

## 🏛️ FedRAMP / GovCloud Usage

This tool is **approved for PS migration engagements** where:
- ServiceNow is on GovCloud
- JSM is on Atlassian Government Cloud (AGC)
- Rovo Dev runs on the consultant's commercial machine

**Architecture:**
```
PS Consultant Mac (commercial)
  └── Rovo CLI / RoHub
       ├── Parses SN XML locally (never leaves consultant's machine)
       └── REST API calls (HTTPS only) ──► JSM (*.atlassian-us-gov-mod.net)
```

See [`references/fedramp-guide.md`](references/fedramp-guide.md) for the complete:
- Pre-engagement checklist
- Required API token scopes
- Post-migration cleanup checklist
- Data handling guidelines

---

## 📁 File Structure

```
~/.rovodev/skills/jsm-workflow-builder/
├── SKILL.md                       # Rovo Dev skill entry point
├── scripts/
│   ├── sn_to_jsm.py              # Main orchestrator (start here)
│   ├── sn_xml_parser.py          # ServiceNow XML parser
│   └── jsm_creator.py            # JSM REST API creator
├── references/
│   ├── servicenow-mapping.md     # SN → JSM concept mapping table
│   ├── workflow-api.md           # Jira Workflow API reference
│   ├── automation-api.md         # Jira Automation API reference
│   ├── approval-api.md           # JSM Approval API reference
│   ├── sla-api.md                # JSM SLA API reference
│   └── fedramp-guide.md          # FedRAMP engagement checklist
└── assets/
    ├── automation-template.json  # Automation rule import template
    └── approval-template.json    # Approval workflow template
```

---

## 🔧 Supported ServiceNow XML Types

| XML Type | Detection | What's Extracted |
|----------|-----------|-----------------|
| Flow Designer Export | `sys_hub_flow` tags | Triggers, steps, approvals, notifications, conditions |
| Update Set | `sys_remote_update_set` | Metadata, scope, name, description |
| Catalog Item | `sc_cat_item` | Variables, categories, workflow associations |
| Legacy Workflow | `wf_workflow` | Activities, transitions, conditions, post-functions |

---

## 📞 Support & Contributing

Built by Atlassian Professional Services — for use during customer JSM migrations.

- **Slack:** `#jsm-migration` (internal)
- **Issues:** [GitHub Issues](https://github.com/vankolekar-dev/sn-jsm-migration-skill/issues)
- **Contributions:** PRs welcome — see `SKILL.md` for architecture notes

---

*Built with Rovo Dev · Atlassian Professional Services*
