from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os, tempfile, uuid, datetime, pathlib, logging

# Optional Google libs
try:
    from google.cloud import storage, vision, firestore
except Exception:
    storage = vision = firestore = None

app = Flask(__name__)
CORS(app)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))




UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/tmp/docrec_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

GCS_BUCKET = os.environ.get("GCS_BUCKET")  # optional
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "local-docrec")

# Initialize optional clients
storage_client = storage.Client() if storage else None
vision_client = vision.ImageAnnotatorClient() if vision else None
firestore_client = firestore.Client(project=PROJECT_ID) if firestore else None

logger = logging.getLogger("docrec")
logging.basicConfig(level=logging.INFO)

@app.route("/", methods=["GET"])
def serve_index():
    # serve index.html from project root
    return send_from_directory(ROOT_DIR, "index.html")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "file missing"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "empty filename"}), 400

    # save to local disk
    ext = pathlib.Path(f.filename).suffix or ".png"
    local_name = f"{uuid.uuid4().hex}{ext}"
    local_path = os.path.join(UPLOAD_DIR, local_name)
    f.save(local_path)
    logger.info("Saved upload to %s", local_path)

    # Read bytes for OCR / upload
    with open(local_path, "rb") as fh:
        img_bytes = fh.read()

    # OCR via Vision (if configured). If Vision not available, leave empty string.
    ocr_text = ""
    if vision_client:
        try:
            image = vision.Image(content=img_bytes)
            resp = vision_client.document_text_detection(image=image)
            if resp.error and resp.error.message:
                logger.warning("Vision error: %s", resp.error.message)
            ocr_text = resp.full_text_annotation.text if resp.full_text_annotation else ""
        except Exception as e:
            logger.exception("Vision OCR failed: %s", e)
            ocr_text = ""

    # Optional upload to GCS
    gcs_path = None
    if GCS_BUCKET and storage_client:
        try:
            bucket = storage_client.bucket(GCS_BUCKET)
            blob_name = f"captures/{local_name}"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(local_path, content_type="image/png")
            gcs_path = f"gs://{GCS_BUCKET}/{blob_name}"
            logger.info("Uploaded to GCS: %s", gcs_path)
        except Exception as e:
            logger.exception("GCS upload failed: %s", e)
            gcs_path = None

    # Save metadata to Firestore (if client available)
    record = {
        "filename": f.filename,
        "local_path": local_path,
        "gcs_path": gcs_path,
        "ocr_text": ocr_text,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    doc_id = None
    if firestore_client:
        try:
            doc_ref = firestore_client.collection("documents").document()
            doc_ref.set(record)
            doc_id = doc_ref.id
            logger.info("Saved metadata to Firestore id=%s", doc_id)
        except Exception as e:
            logger.exception("Firestore write failed: %s", e)

    return jsonify({
        "id": doc_id,
        "filename": f.filename,
        "gcs_path": gcs_path,
        "ocr_snippet": (ocr_text[:600] + "...") if ocr_text else "",
        "created_at": record["created_at"]
    }), 201

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)