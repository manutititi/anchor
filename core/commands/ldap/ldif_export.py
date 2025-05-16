from core.utils.colors import green

def export_ldif(entries, path):
    with open(path, "w") as f:
        f.write("version: 1\n\n")
        for entry in entries:
            f.write(f"dn: {entry.entry_dn}\n")
            for attr, val in entry.entry_attributes_as_dict.items():
                if isinstance(val, list):
                    for item in val:
                        f.write(f"{attr}: {item}\n")
                else:
                    f.write(f"{attr}: {val}\n")
            f.write("\n")
    print(green(f"✅ Exported {len(entries)} entries to {path}"))
