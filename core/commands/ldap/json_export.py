import json
from core.utils.colors import green

def clean_value(val):
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except UnicodeDecodeError:
            return val.hex()
    return val

def export_json(entries, output=None):
    data = []
    for entry in entries:
        record = {"dn": entry.entry_dn}
        for attr, val in entry.entry_attributes_as_dict.items():
            if isinstance(val, list):
                val = [clean_value(v) for v in val]
                record[attr] = val if len(val) > 1 else val[0]  # ← uno solo → string
            else:
                record[attr] = clean_value(val)
        data.append(record)

    if isinstance(output, str):
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(green(f"✅ Exported {len(data)} entries to {output}"))
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))
