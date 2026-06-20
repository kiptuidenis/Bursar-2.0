import os
import re
import subprocess
import tempfile
import sys

# Get the project root folder directory
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
static_dir = os.path.join(base_dir, "app", "static")

has_errors = False

def run_node_check(file_path):
    try:
        res = subprocess.run(["node", "--check", file_path], capture_output=True, text=True)
        if res.returncode == 0:
            return True, ""
        else:
            return False, res.stderr
    except FileNotFoundError:
        print("ERROR: Node.js ('node') executable was not found. Please install Node.js.")
        sys.exit(1)

# 1. Audit static JS files
js_dir = os.path.join(static_dir, "js")
if os.path.exists(js_dir):
    for root, _, files in os.walk(js_dir):
        for file in files:
            if file.endswith(".js"):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, base_dir)
                print(f"Auditing static JS file: {rel_path}...")
                ok, err = run_node_check(full_path)
                if not ok:
                    print(f"[ERROR] SYNTAX ERROR in {rel_path}:\n{err}")
                    has_errors = True
                else:
                    print(f"[OK] {rel_path} is syntactically valid.")

# 2. Audit inline scripts inside HTML files
for root, _, files in os.walk(static_dir):
    for file in files:
        if file.endswith(".html"):
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, base_dir)
            
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            scripts = re.findall(r"<script>(.*?)</script>", content, re.DOTALL)
            if not scripts:
                continue
                
            print(f"Auditing inline scripts in: {rel_path} ({len(scripts)} script block(s))...")
            
            for idx, script_content in enumerate(scripts, 1):
                if not script_content.strip():
                    continue
                
                # Write script block to temporary file
                with tempfile.NamedTemporaryFile(suffix=".js", delete=False, mode="w", encoding="utf-8") as tmp:
                    tmp.write(script_content)
                    tmp_name = tmp.name
                    
                try:
                    ok, err = run_node_check(tmp_name)
                    if not ok:
                        print(f"[ERROR] SYNTAX ERROR in inline script block #{idx} of {rel_path}:\n{err}")
                        has_errors = True
                    else:
                        print(f"[OK] Inline script block #{idx} in {rel_path} is syntactically valid.")
                finally:
                    if os.path.exists(tmp_name):
                        os.remove(tmp_name)

if has_errors:
    print("\nAudit failed: Syntax errors were detected in your static assets.")
    sys.exit(1)
else:
    print("\nAudit passed: All static files and inline scripts are syntactically valid! [SUCCESS]")
    sys.exit(0)
