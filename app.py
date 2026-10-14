from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from comparator import compare_images, find_duplicates


ROOT = Path(__file__).resolve().parent
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


class ImageComparatorHandler(BaseHTTPRequestHandler):
    server_version = "ImageComparator/1.0"

    def do_GET(self) -> None:
        requested = unquote(self.path.split("?", 1)[0])
        if requested in {"/", "/index.html"}:
            self.send_file(ROOT / "index.html")
            return
        self.send_file(ROOT / requested.lstrip("/"))

    def do_POST(self) -> None:
        if self.path == "/api/compare":
            self.handle_compare()
            return
        self.send_json({"error": "Route inconnue."}, status=404)

    def handle_compare(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)

        try:
            files = parse_multipart(body, content_type)
            left = files["left"]
            right = files["right"]
            result = compare_images(left["data"], right["data"], left["filename"], right["filename"])
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)
            return

        self.send_json(result)

    def send_file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            resolved.relative_to(ROOT)
        except ValueError:
            self.send_error(403)
            return

        if not resolved.exists() or not resolved.is_file():
            self.send_error(404)
            return

        content_type = STATIC_TYPES.get(resolved.suffix.lower()) or mimetypes.guess_type(resolved)[0] or "application/octet-stream"
        data = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), format % args))


def parse_multipart(body: bytes, content_type: str) -> dict[str, dict[str, bytes | str]]:
    marker = "boundary="
    if marker not in content_type:
        raise ValueError("La requête ne contient pas de fichiers.")

    boundary = ("--" + content_type.split(marker, 1)[1].strip().strip('"')).encode("utf-8")
    files: dict[str, dict[str, bytes | str]] = {}

    for part in body.split(boundary):
        part = part.strip()
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].strip()
        if b"\r\n\r\n" not in part:
            continue

        raw_headers, data = part.split(b"\r\n\r\n", 1)
        headers = raw_headers.decode("utf-8", errors="replace")
        disposition = next((line for line in headers.split("\r\n") if line.lower().startswith("content-disposition:")), "")
        name = extract_disposition_value(disposition, "name")
        filename = extract_disposition_value(disposition, "filename") or name
        if name in {"left", "right"}:
            files[name] = {"filename": filename, "data": data.rstrip(b"\r\n")}

    if "left" not in files or "right" not in files:
        raise ValueError("Ajoute deux images avant de lancer la comparaison.")
    return files


def extract_disposition_value(disposition: str, key: str) -> str:
    needle = key + '="'
    if needle not in disposition:
        return ""
    return disposition.split(needle, 1)[1].split('"', 1)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Comparateur d'images local")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--find-duplicates", metavar="DOSSIER", help="cherche les images très similaires dans un dossier")
    parser.add_argument("--threshold", type=int, default=8, help="distance pHash maximale pour les doublons")
    args = parser.parse_args()

    if args.find_duplicates:
        print(json.dumps(find_duplicates(args.find_duplicates, args.threshold), ensure_ascii=False, indent=2))
        return

    server = ThreadingHTTPServer((args.host, args.port), ImageComparatorHandler)
    print(f"Comparateur d'images lancé sur http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
