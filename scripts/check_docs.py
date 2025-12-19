import os
import re
import sys
from pathlib import Path

DOCS_DIR = Path("docs")

def check_structure():
    """Ensure critical documentation structure exists."""
    required = [
        DOCS_DIR / "00-overview" / "00-README.md",
        DOCS_DIR / "00-overview" / "04-docs-dod.md",
        DOCS_DIR / "02-business-rules" / "00-rules-index.md",
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        print(f"❌ Missing critical docs: {[str(p) for p in missing]}")
        return False
    print("✅ Critical structure present.")
    return True

def check_links():
    """Simple check for broken relative links in Markdown files."""
    broken_links = []
    markdown_files = list(DOCS_DIR.rglob("*.md"))
    
    link_pattern = re.compile(r'\[.*?\]\((.*?)\)')
    
    for md_file in markdown_files:
        content = md_file.read_text(encoding='utf-8')
        links = link_pattern.findall(content)
        
        for link in links:
            if link.startswith('http') or link.startswith('#') or link.startswith('mailto:'):
                continue
            
            # Remove anchors
            link_path = link.split('#')[0]
            if not link_path:
                continue
                
            # Resolve relative path
            target = (md_file.parent / link_path).resolve()
            
            if not target.exists():
                broken_links.append(f"{md_file}: Broken link '{link}'")

    if broken_links:
        print("❌ Found broken links:")
        for error in broken_links:
            print(f"  - {error}")
        return False
    
    print(f"✅ Checked {len(markdown_files)} files. No broken links found.")
    return True

def main():
    if not DOCS_DIR.exists():
        print("❌ /docs directory not found!")
        sys.exit(1)
        
    structure_ok = check_structure()
    links_ok = check_links()
    
    if not (structure_ok and links_ok):
        sys.exit(1)
        
    print("🎉 Docs check passed!")

if __name__ == "__main__":
    main()
