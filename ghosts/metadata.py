import json
import string
from hashlib import sha256
from xml.sax.saxutils import escape

import piexif

XMP_HEADER = b"http://ns.adobe.com/xap/1.0/\x00"


def canary_for(image_id: str, length: int = 12) -> str:
    seed = f"container-ghosts-canary:{image_id}"
    alphabet = string.ascii_uppercase + string.digits
    digest = sha256(seed.encode("utf-8")).digest()
    return "GHOSTCANARY_" + "".join(alphabet[b % len(alphabet)] for b in digest[:length])


def camera_exif(canary: str) -> bytes:
    comment = b"ASCII" + b"\x00" * 3 + b"camera capture fixture; " + canary.encode("ascii")
    data = {
        "0th": {
            piexif.ImageIFD.Make: b"Canon",
            piexif.ImageIFD.Model: b"Canon EOS R6",
            piexif.ImageIFD.DateTime: b"2026:01:14 09:30:00",
        },
        "Exif": {
            piexif.ExifIFD.ExposureTime: (1, 125),
            piexif.ExifIFD.FNumber: (28, 10),
            piexif.ExifIFD.ISOSpeedRatings: 200,
            piexif.ExifIFD.DateTimeOriginal: b"2026:01:14 09:30:00",
            piexif.ExifIFD.FocalLength: (35, 1),
            piexif.ExifIFD.LensModel: b"RF24-105mm F4 L IS USM",
            piexif.ExifIFD.UserComment: comment,
        },
        "GPS": {}, "1st": {}, "thumbnail": None,
    }
    return piexif.dump(data)


def ai_exif(canary: str) -> bytes:
    comment = b"ASCII" + b"\x00" * 3 + b"trainedAlgorithmicMedia fixture; " + canary.encode("ascii")
    data = {
        "0th": {
            piexif.ImageIFD.Make: b"ComfyUI",
            piexif.ImageIFD.Model: b"FLUX.1-schnell",
            piexif.ImageIFD.Software: b"ComfyUI 0.3.x synthetic workflow",
            piexif.ImageIFD.ImageDescription: b"AI-generated procedural test image; " + canary.encode("ascii"),
        },
        "Exif": {piexif.ExifIFD.UserComment: comment},
        "GPS": {}, "1st": {}, "thumbnail": None,
    }
    return piexif.dump(data)


def _xmp_body(kind: str, canary: str) -> str:
    esc = escape(canary)
    if kind == "camera":
        fields = """
  <xmp:CreatorTool>Canon EOS R6 firmware fixture</xmp:CreatorTool>
  <xmp:CreateDate>2026-01-14T09:30:00Z</xmp:CreateDate>
  <exif:Make>Canon</exif:Make>
  <exif:Model>Canon EOS R6</exif:Model>
  <Iptc4xmpExt:DigitalSourceType>http://cv.iptc.org/newscodes/digitalsourcetype/digitalCapture</Iptc4xmpExt:DigitalSourceType>
  <dc:description><rdf:Alt><rdf:li xml:lang=\"x-default\">camera provenance fixture CANARY</rdf:li></rdf:Alt></dc:description>"""
    elif kind == "ai":
        fields = """
  <xmp:CreatorTool>ComfyUI 0.3.x</xmp:CreatorTool>
  <xmp:CreateDate>2026-01-14T09:30:00Z</xmp:CreateDate>
  <Iptc4xmpExt:DigitalSourceType>http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia</Iptc4xmpExt:DigitalSourceType>
  <Iptc4xmpExt:AISystemUsed>FLUX.1-schnell procedural fixture</Iptc4xmpExt:AISystemUsed>
  <Iptc4xmpExt:AISystemVersionUsed>schnell-fixture</Iptc4xmpExt:AISystemVersionUsed>
  <Iptc4xmpExt:AIPromptInformation>procedural geometric test image</Iptc4xmpExt:AIPromptInformation>
  <dc:description><rdf:Alt><rdf:li xml:lang=\"x-default\">AI provenance fixture CANARY</rdf:li></rdf:Alt></dc:description>"""
    else:
        fields = """
  <xmp:CreatorTool>container-ghosts fixture generator</xmp:CreatorTool>
  <dc:description><rdf:Alt><rdf:li xml:lang=\"x-default\">neutral container fixture CANARY</rdf:li></rdf:Alt></dc:description>"""
    return fields.replace("CANARY", esc)


def xmp_packet(kind: str, canary: str) -> bytes:
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:exif="http://ns.adobe.com/exif/1.0/" xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/">
 <rdf:RDF>
  <rdf:Description rdf:about="">{_xmp_body(kind, canary)}
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>'''
    return xml.encode("utf-8")


def xmp_app1_payload(kind: str, canary: str) -> bytes:
    return XMP_HEADER + xmp_packet(kind, canary)


def a1111_parameters(canary: str) -> str:
    return (
        "procedural geometric test image\n"
        "Steps: 4, Sampler: euler, CFG scale: 1.0, Seed: 448448, "
        "Model: flux1-schnell-fixture, Version: a1111-fixture, Canary: " + canary
    )


def comfy_workflow(canary: str) -> str:
    workflow = {
        "fixture": True,
        "canary": canary,
        "nodes": {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-schnell-fixture.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {"seed": 448448, "steps": 4, "cfg": 1.0}},
        },
    }
    return json.dumps(workflow, sort_keys=True, separators=(",", ":"))
