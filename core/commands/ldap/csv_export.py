import csv
from core.utils.colors import green

def clean_value(val):
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except UnicodeDecodeError:
            return val.hex()
    return val

def extract_uid(dn_or_uid):
    """
    Si es un DN tipo uid=ana,ou=users,... → devuelve 'ana'.
    Si ya es un uid directo, lo devuelve sin tocar.
    """
    if "=" in dn_or_uid and "," in dn_or_uid:
        first = dn_or_uid.split(",")[0]
        if first.startswith("uid="):
            return first.split("=")[1]
    return dn_or_uid  # fallback

def export_groups(entries, member_attr="member", output="groups.csv"):
    group_map = {}  # group name → list of member uids

    for entry in entries:
        group_name = entry["cn"].value if "cn" in entry else entry.entry_dn
        members = entry[member_attr].values if member_attr in entry else []
        uids = [extract_uid(m) for m in members]
        group_map[group_name] = uids

    # construir conjunto de todos los uids
    all_uids = sorted(set(uid for members in group_map.values() for uid in members))
    groups = sorted(group_map.keys())

    # escribir CSV transpuesto
    with open(output, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(groups)

        for uid in all_uids:
            row = [uid if uid in group_map[g] else "" for g in groups]
            writer.writerow(row)

    print(green(f"✅ Exported group membership matrix to {output}"))

def export_users(entries, attr_map=None, output="users.csv"):
    """
    attr_map: diccionario opcional {ldap_attr: label}. Si es None, se detectan todos los atributos.
    """
    all_fields = set()
    users = []

    for entry in entries:
        row = {"dn": entry.entry_dn}
        attrs = entry.entry_attributes_as_dict

        for attr, val in attrs.items():
            val = val if isinstance(val, list) else [val]
            val = [clean_value(v) for v in val if v is not None]

            if attr_map:
                label = attr_map.get(attr, attr)
            else:
                label = attr

            all_fields.add(label)
            row[label] = ", ".join(val)

        users.append(row)

    # campos ordenados: primero dn, luego los demás
    headers = ["dn"] + sorted(all_fields - {"dn"})

    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for user in users:
            writer.writerow({k: user.get(k, "") for k in headers})

    print(green(f"✅ Exported {len(users)} users to {output}"))
