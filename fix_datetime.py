import os
import re

directories = ['scrapers', 'pipeline', 'storage', 'scripts']
files_to_fix = ['crash_test.py', 'main.py']

for d in directories:
    if os.path.exists(d):
        for root, _, files in os.walk(d):
            for f in files:
                if f.endswith('.py'):
                    files_to_fix.append(os.path.join(root, f))

for fpath in files_to_fix:
    if not os.path.exists(fpath): continue
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    changed = False
    if 'datetime.utcnow()' in content:
        content = content.replace('datetime.utcnow()', 'datetime.now(timezone.utc)')
        changed = True
        
        # Ensure timezone is imported
        if 'from datetime import datetime' in content and 'timezone' not in content:
            content = content.replace('from datetime import datetime', 'from datetime import datetime, timezone')
        elif 'import datetime' in content and 'from datetime import timezone' not in content:
            content = re.sub(r'(import datetime[^\n]*)', r'\1\nfrom datetime import timezone', content, count=1)
            
    if changed:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed datetime in {fpath}")

print("Datetime deprecation fix complete.")
