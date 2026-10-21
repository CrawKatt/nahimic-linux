"""Extract and verify the runtime data required by supported hardware."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile


def extract(swc, settings, lenovo, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(Path(__file__).with_name("runtime-sha256.json").read_text())
    with tempfile.TemporaryDirectory(prefix=".extract-", dir=output) as temporary:
        work = Path(temporary)
        subprocess.run(["cabextract", "-q", "-d", str(work / "vendor"), str(swc)], check=True)
        data = Path(settings).read_bytes()
        start = data.find(b"PK\x03\x04")
        end = data.find(b"PK\x05\x06", start)
        if start < 0 or end < 0:
            raise ValueError("Runtime settings archive is absent")
        comment = struct.unpack_from("<H", data, end + 20)[0]
        with zipfile.ZipFile(io.BytesIO(data[start:end + 22 + comment])) as archive:
            cab = archive.read("Drivers\\EXT\\AIstone\\APO4\\NH3CNXTProductSettings.cab")
        (work / "settings.cab").write_bytes(cab)
        subprocess.run(["cabextract", "-q", "-d", str(work / "factory"), str(work / "settings.cab")], check=True)
        # DS575151 / Realtek_6.0.9879.1_SST12181: 0257/17AA3DCB selects CAB 0.
        lenovo_cab = "code$GetExtractPath$/Audio9879/Driver/Nahimic/ExtINF_Path/NH3ProductSettings0.cab"
        subprocess.run(["innoextract", "--silent", "--include", lenovo_cab,
                        "--output-dir", str(work / "lenovo"), str(lenovo)], check=True)
        subprocess.run(["cabextract", "-q", "-d", str(work / "factory/17AA3DCB"),
                        str(work / "lenovo" / lenovo_cab)], check=True)
        for name, expected in manifest.items():
            source = work / name
            if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise ValueError("Runtime checksum mismatch: " + name)
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


if __name__ == "__main__":
    extract(*sys.argv[1:])
