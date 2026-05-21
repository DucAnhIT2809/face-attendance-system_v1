# Online Database And Training Setup

## Recommended Stack

- PostgreSQL online: Supabase, Neon, Render PostgreSQL, or Railway PostgreSQL.
- Face image storage: S3-compatible object storage. Supabase Storage is a good default because it gives PostgreSQL and Storage in one project.
- Backend stores only metadata in PostgreSQL. Face images are saved as local paths in dev or `s3://bucket/key` / public URLs in production.

## PostgreSQL Migration

1. Create a managed PostgreSQL database.
2. Run `database/schema.sql`.
3. Optionally run `database/seed_dev.sql` for development accounts/data.
4. Set backend environment:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DB_NAME
JWT_SECRET=replace-with-a-long-random-secret
CORS_ORIGINS=https://your-frontend-domain
```

Do not commit `.env` files to GitHub.

You can also import from the command line:

```bash
DATABASE_URL="postgresql://USER:PASSWORD@HOST:PORT/DB_NAME" \
  bash database/import_online_db.sh

IMPORT_SEED_DEV=1 DATABASE_URL="postgresql://USER:PASSWORD@HOST:PORT/DB_NAME" \
  bash database/import_online_db.sh
```

## Object Storage

For local development:

```env
STORAGE_BACKEND=local
UPLOAD_ROOT=uploads
```

For S3-compatible storage:

```env
STORAGE_BACKEND=s3
S3_BUCKET=your-bucket
S3_REGION=ap-southeast-1
S3_ENDPOINT_URL=https://your-s3-compatible-endpoint
S3_ACCESS_KEY_ID=your-access-key
S3_SECRET_ACCESS_KEY=your-secret-key
S3_PREFIX=face-attendance
STORAGE_PUBLIC_BASE_URL=https://public-base-url/your-bucket
```

If `STORAGE_PUBLIC_BASE_URL` is configured, uploaded image metadata stores public HTTPS URLs. Otherwise it stores `s3://bucket/key`.

## Per-Class Training

From the repository root, using **`modelcore/Model_v2`** (YOLOv8s-face defaults in pipeline; place `yolov8s-face.pt` under `modelcore/Model_v2/` or `modelcore/Model_v2/detect_tracking/`).

Build a training folder for one class (PostgreSQL URL):

```bash
cd modelcore/Model_v2
python -m face_pipeline build-training \
  --database-url "$DATABASE_URL" \
  --class-code INT1407_1 \
  --output-dir /tmp/TrainingSelected/INT1407_1 \
  --overwrite
```

Export embeddings for that class:

```bash
cd modelcore/Model_v2
python -m face_pipeline export-embeddings \
  --checkpoint arcface_runs/arcface_resnet18.pth \
  --gallery-dir /tmp/TrainingAugmented/INT1407_1 \
  --class-code INT1407_1 \
  --class-output-root arcface_runs/classes
```

At runtime, live attendance first looks for:

```text
<CLASS_EMBEDDING_ROOT>/<class_code>/face_db.pt
```

If it exists, that class-specific embedding database is used. If not, the backend falls back to `FACE_EMBEDDING_DB`.
