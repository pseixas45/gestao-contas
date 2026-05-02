"""Importa todos os arquivos da pasta extratos/ via API REST.

Para cada arquivo:
1. Upload (cria batch, detecta colunas via template)
2. Process (com skip_duplicates=true)
3. Reporta resultado: importadas, duplicadas, erros
"""
import os
import sys
import requests
from pathlib import Path

API_URL = "http://localhost:8002"
USERNAME = "pseixas"
PASSWORD = "pseixas123"

# Mapeamento de arquivo → account_id (baseado no padrão do nome)
def detect_account(filename: str) -> int | None:
    f = filename.lower()
    if f.startswith("itau"):
        return 5  # Itaú
    if f.startswith("c6 master") or f.startswith("master"):
        return 6  # Master
    if f.startswith("c6 ") and "master" not in f:
        return 1  # C6
    if f.startswith("visa"):
        return 8  # Visa
    if f.startswith("xp visa"):
        return 10  # XPVisa
    return None


# Arquivos a pular (PDFs, saldos, versões antigas que duplicariam)
SKIP = {
    "Saldos 260305.xlsx",
    "Master Fev.pdf",
    "Master Jan.pdf",
    "Visa Fev.pdf",
    "Visa Jan.pdf",
    "Visa Mar.pdf",
    "Extrato (1).pdf",
    # Versões antigas do Itaú (já existem versões mais novas)
    "Itau 260305 v1.xlsx",
    "Itau 260305 v2.xls",
    "Itau 260305.xls",
    # Versões antigas duplicadas
    "Master 260220 - 260301.xlsx",
    "Master fatura-20260220.csv",
    "Master fatura-20260320.csv",  # tem v2 mais nova
    "Visa 260206.xlsx",
    "Visa fatura-20260106 v2.csv",  # já importado
    "Visa fatura-20260306.csv",  # tem v2
}


def login() -> str:
    r = requests.post(
        f"{API_URL}/api/v1/auth/login",
        data={"username": USERNAME, "password": PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def import_file(token: str, file_path: Path, account_id: int) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    result = {"file": file_path.name, "account_id": account_id, "stage": "init"}

    # 1. Upload
    with open(file_path, "rb") as f:
        upload_resp = requests.post(
            f"{API_URL}/api/v1/imports/upload",
            files={"file": (file_path.name, f)},
            data={"account_id": account_id},
            headers=headers,
        )
    if upload_resp.status_code != 200:
        result["stage"] = "upload"
        result["error"] = f"HTTP {upload_resp.status_code}: {upload_resp.text[:200]}"
        return result

    upload_data = upload_resp.json()
    batch_id = upload_data["batch_id"]
    mapping = upload_data.get("detected_mapping")
    has_template = upload_data.get("has_template", False)
    result["batch_id"] = batch_id
    result["has_template"] = has_template

    if not mapping or not mapping.get("date_column") or not mapping.get("description_column"):
        result["stage"] = "mapping"
        result["error"] = f"colunas não detectadas (template={has_template})"
        return result

    # 2. Process
    process_payload = {
        "batch_id": batch_id,
        "account_id": account_id,
        "column_mapping": mapping,
        "validate_balance": False,
        "skip_duplicates": True,
    }
    process_resp = requests.post(
        f"{API_URL}/api/v1/imports/process",
        json=process_payload,
        headers=headers,
    )
    if process_resp.status_code != 200:
        result["stage"] = "process"
        result["error"] = f"HTTP {process_resp.status_code}: {process_resp.text[:200]}"
        return result

    pdata = process_resp.json()
    result["stage"] = "done"
    result["success"] = pdata.get("success", False)
    result["imported"] = pdata.get("imported_count", 0)
    result["duplicates"] = pdata.get("duplicate_count", 0)
    result["errors"] = pdata.get("error_count", 0)
    return result


def main():
    extratos_dir = Path(r"c:\Users\paulo\gestao-contas\extratos")
    if not extratos_dir.exists():
        print(f"ERRO: pasta {extratos_dir} não encontrada")
        return 1

    print("Fazendo login...")
    token = login()
    print("OK\n")

    files = sorted(extratos_dir.iterdir())
    results = []

    for f in files:
        if not f.is_file():
            continue
        if f.name in SKIP:
            print(f"SKIP: {f.name} (na lista de exclusão)")
            continue
        if f.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
            print(f"SKIP: {f.name} (formato não suportado)")
            continue

        account_id = detect_account(f.name)
        if account_id is None:
            print(f"SKIP: {f.name} (não consegui detectar a conta)")
            continue

        print(f"Importando: {f.name} (conta {account_id})...", end=" ", flush=True)
        try:
            r = import_file(token, f, account_id)
            results.append(r)
            if r.get("stage") == "done" and r.get("success"):
                print(f"OK [imp={r['imported']} dup={r['duplicates']} err={r['errors']}]")
            elif r.get("stage") == "done":
                print(f"PARCIAL [imp={r['imported']} dup={r['duplicates']} err={r['errors']}]")
            else:
                print(f"FALHA em '{r.get('stage')}': {r.get('error', '?')}")
        except Exception as e:
            print(f"EXCEÇÃO: {e}")
            results.append({"file": f.name, "stage": "exception", "error": str(e)})

    # Sumário
    print("\n" + "=" * 60)
    print("RESUMO FINAL")
    print("=" * 60)
    total_imp = sum(r.get("imported", 0) for r in results)
    total_dup = sum(r.get("duplicates", 0) for r in results)
    total_err = sum(r.get("errors", 0) for r in results)
    failed = [r for r in results if r.get("stage") != "done"]

    print(f"Arquivos processados: {len(results)}")
    print(f"Total importado:      {total_imp}")
    print(f"Total duplicado:      {total_dup}")
    print(f"Total com erro:       {total_err}")
    print(f"Arquivos com falha:   {len(failed)}")

    if failed:
        print("\nFALHAS:")
        for r in failed:
            print(f"  - {r['file']}: [{r.get('stage','?')}] {r.get('error','?')}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
