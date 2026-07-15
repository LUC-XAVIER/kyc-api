r"""Submit a verification from image files — no camera required.

Stands in for the agent's camera capture on machines with no webcam (e.g. a
VM), driving the real endpoint so the whole ML pipeline runs: OCR -> liveness
-> face match -> duplicate check. Prints the verdict plus the per-stage
breakdown read back from the API.

The API must already be running (``uv run uvicorn app.main:app --reload``).

Authenticate either as a user (agent or manager) or with an API key:

    uv run python -m scripts.verify_smoke \
        --front docs/Identifiers/testImages/FrontNIC.jpeg \
        --back docs/Identifiers/testImages/backNIC.jpeg \
        --selfie docs/Identifiers/testImages/selfie.jpeg \
        --identifier manager@camfinance.cm --pin 123456

    uv run python -m scripts.verify_smoke --front f.jpg --selfie s.jpg \
        --doc-type PASSPORT --api-key kyc_live_...

NOTE: this writes a real verification row to whichever database the API is
pointed at.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx


def _login(base: str, identifier: str, pin: str) -> str:
    """Exchange identifier + PIN for a bearer token."""
    resp = httpx.post(
        f"{base}/auth/login",
        json={"identifier": identifier, "pin": pin},
        timeout=30,
    )
    if resp.status_code != 200:
        sys.exit(f"Login failed ({resp.status_code}): {resp.text}")
    return str(resp.json()["access_token"])


def _submit(
    base: str,
    headers: dict[str, str],
    *,
    client_id: str,
    doc_type: str,
    front: Path,
    selfie: Path,
    back: Path | None,
) -> httpx.Response:
    """POST the images to /kyc/verify as multipart form-data."""
    files = {
        "id_front": (front.name, front.read_bytes(), "image/jpeg"),
        "selfie": (selfie.name, selfie.read_bytes(), "image/jpeg"),
    }
    if back is not None:
        files["id_back"] = (back.name, back.read_bytes(), "image/jpeg")
    return httpx.post(
        f"{base}/kyc/verify",
        data={"client_id": client_id, "document_type": doc_type},
        files=files,
        headers=headers,
        timeout=180,  # the ML pipeline is slow on first load (model warm-up)
    )


def _print_detail(base: str, headers: dict[str, str], vid: str) -> None:
    """Read the verification back and show each pipeline stage."""
    resp = httpx.get(
        f"{base}/kyc/verifications/{vid}", headers=headers, timeout=30
    )
    if resp.status_code != 200:
        print(f"\n(could not read detail: {resp.status_code} {resp.text})")
        return
    d = resp.json()
    print("\n--- pipeline stages ---")
    print("OCR extracted :", json.dumps(d.get("extracted_data"), indent=2))
    print("liveness      :", json.dumps(d.get("liveness_result"), indent=2))
    print("face match    :", json.dumps(d.get("face_match_result"), indent=2))
    print("duplicates    :", json.dumps(d.get("duplicate_flags"), indent=2))


def main() -> None:
    """Parse arguments and run one verification end-to-end."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--front", type=Path, required=True)
    parser.add_argument("--back", type=Path, default=None)
    parser.add_argument("--selfie", type=Path, required=True)
    parser.add_argument(
        "--doc-type", default="NIC", choices=["NIC", "PASSPORT"]
    )
    parser.add_argument("--client-id", default="CLT-SMOKE-001")
    parser.add_argument("--api-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--identifier", default=None, help="email or phone")
    parser.add_argument("--pin", default=None)
    args = parser.parse_args()

    for path in (args.front, args.selfie, args.back):
        if path is not None and not path.is_file():
            sys.exit(f"No such image: {path}")
    if args.doc_type == "NIC" and args.back is None:
        sys.exit("A NIC needs --back (the back of the card carries the MRZ).")

    if args.api_key:
        headers = {"X-API-Key": args.api_key}
    elif args.identifier and args.pin:
        token = _login(args.api_url, args.identifier, args.pin)
        headers = {"Authorization": f"Bearer {token}"}
    else:
        sys.exit("Pass --api-key, or --identifier with --pin.")

    print(f"Submitting {args.doc_type} for {args.client_id} …")
    resp = _submit(
        args.api_url,
        headers,
        client_id=args.client_id,
        doc_type=args.doc_type,
        front=args.front,
        selfie=args.selfie,
        back=args.back,
    )
    print(f"\nHTTP {resp.status_code}")
    print(json.dumps(resp.json(), indent=2))

    if resp.status_code == 201:
        _print_detail(args.api_url, headers, resp.json()["verification_id"])


if __name__ == "__main__":
    main()
