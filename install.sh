#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# SN → JSM Migration Skill — One-Command Installer
# Usage: curl -sSL https://raw.githubusercontent.com/vankolekar-dev/sn-jsm-migration-skill/main/install.sh | bash
# ─────────────────────────────────────────────────────────────────────────────
set -e

SKILL_DIR="$HOME/.rovodev/skills/jsm-workflow-builder"
REPO="https://raw.githubusercontent.com/vankolekar-dev/sn-jsm-migration-skill/main"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo ""
echo "🔄 ServiceNow → JSM Migration Skill Installer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check Python
if ! command -v python3 &>/dev/null; then
  echo -e "${RED}❌ Python 3 is required. Install from https://python.org${NC}"
  exit 1
fi
echo -e "${GREEN}✅ Python 3 found: $(python3 --version)${NC}"

# Create skill directory structure
echo "📁 Creating skill directory..."
mkdir -p "$SKILL_DIR/scripts"
mkdir -p "$SKILL_DIR/references"
mkdir -p "$SKILL_DIR/assets"

# Download files
echo "⬇️  Downloading skill files..."

FILES=(
  "SKILL.md"
  "scripts/sn_to_jsm.py"
  "scripts/sn_xml_parser.py"
  "scripts/jsm_creator.py"
  "references/servicenow-mapping.md"
  "references/workflow-api.md"
  "references/automation-api.md"
  "references/approval-api.md"
  "references/sla-api.md"
  "assets/automation-template.json"
  "assets/approval-template.json"
)

for file in "${FILES[@]}"; do
  dir=$(dirname "$SKILL_DIR/$file")
  mkdir -p "$dir"
  if curl -sSf "$REPO/$file" -o "$SKILL_DIR/$file" 2>/dev/null; then
    echo -e "  ${GREEN}✅${NC} $file"
  else
    echo -e "  ${YELLOW}⚠️  Skipped (not found): $file${NC}"
  fi
done

# Make scripts executable
chmod +x "$SKILL_DIR/scripts/"*.py 2>/dev/null || true

# Install Python dependencies
echo ""
echo "📦 Installing Python dependencies..."
python3 -m pip install --quiet requests 2>/dev/null && \
  echo -e "  ${GREEN}✅ requests${NC}" || \
  echo -e "  ${YELLOW}⚠️  Could not install requests (using stdlib urllib instead)${NC}"

# Verify installation
echo ""
echo "🔍 Verifying installation..."
if python3 "$SKILL_DIR/scripts/sn_to_jsm.py" --help &>/dev/null; then
  echo -e "${GREEN}✅ Skill installed successfully!${NC}"
else
  echo -e "${RED}❌ Verification failed. Check $SKILL_DIR/scripts/sn_to_jsm.py${NC}"
  exit 1
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}🎉 Installation complete!${NC}"
echo ""
echo "📖 Usage:"
echo "   Conversational: Tell Rovo Dev 'Migrate this ServiceNow XML to JSM'"
echo "   Direct script:  python3 ~/.rovodev/skills/jsm-workflow-builder/scripts/sn_to_jsm.py --help"
echo ""
echo "📚 Docs: https://github.com/vankolekar-dev/sn-jsm-migration-skill"
echo ""
