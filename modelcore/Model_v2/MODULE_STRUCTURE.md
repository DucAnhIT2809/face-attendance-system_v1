# Cấu trúc module & pipeline (`face_pipeline`)

Code chính nằm trong package **`Model_v2/face_pipeline/`**. Các file ở `Model_v2/*.py`, `Model_v2/detect_tracking/*.py`, `Model_v2/recognition/*.py` chỉ là **shim** (gọi lại package) để lệnh cũ vẫn chạy được.

## Chạy chuẩn (khuyên dùng)

Từ thư mục gốc repo, **`cd` vào `modelcore/Model_v2`**, rồi:

```bash
cd modelcore/Model_v2
python -m face_pipeline <lenh> [tham so ...]
```

### Lệnh pipeline & từng bước

| Lệnh | Mô tả |
|------|--------|
| `train-full` | **Pipeline đầy đủ:** DB → `TrainingSelected/` → augment → train ArcFace → `face_db.pt` |
| `check-db` | Kiểm tra kết nối PostgreSQL + liệt kê bảng / cột **`yolo_face_attendance`** (và ghi chú nếu có `attendance_records`) |
| `build-training` | Build `TrainingSelected` từ PostgreSQL (`--database-url` hoặc `--db-*`, `--class-code`, `--include-pending`) |
| `augment` | Augment thư mục lớp ảnh |
| `arcface-train` | Train ArcFace |
| `export-embeddings` | Xuất embedding DB (`--class-code` + `--class-output-root` cho từng lớp) |
| `recognize` | Nhận diện một ảnh |
| `detect` | Webcam chỉ detect (mặc định **yolov8s-face**) |
| `track` | Webcam track + nhận diện ArcFace + điểm danh PG (mặc định **yolov8s-face**) |
| `compare-yolo` | So sánh **YOLOv8n-face**, **YOLOv8s-face**, **YOLOv9-c** trên webcam + metrics (`--run-all`) |
| `student-db` | CRUD sinh viên PostgreSQL (giữ nguyên `--command ...`) |

### Ví dụ pipeline huấn luyện từ DB

```bash
cd modelcore/Model_v2
python -m face_pipeline train-full \
  --db-name face_attendance_db \
  --db-user postgres \
  --db-password 1234 \
  --class-code INT1407_1
```

### Ví dụ từng bước

```bash
python -m face_pipeline build-training --database-url "$DATABASE_URL" --class-code INT1407_1 --overwrite
python -m face_pipeline augment --input-dir ../TrainingSelected --output-dir ../TrainingAugmented --overwrite
python -m face_pipeline arcface-train --training-dir ../TrainingAugmented
python -m face_pipeline export-embeddings --checkpoint arcface_runs/arcface_resnet18.pth
```

### Webcam & so sánh YOLO

```bash
python -m face_pipeline detect
python -m face_pipeline track
python -m face_pipeline compare-yolo --run-all --eval-seconds 15
```

### CSDL sinh viên

```bash
python -m face_pipeline student-db --db-name ... --db-user ... --db-password ... --command init-schema
```

## Cây package (logic thật)

```
Model_v2/face_pipeline/
  __init__.py
  __main__.py          # python -m face_pipeline
  paths.py             # REPO_ROOT (= modelcore), MODEL_DIR (= Model_v2), resolve_weight_file()
  detect_tracking/
    yolo_webcam.py
    yolo_track.py
    yolo_compare.py
  recognition/
    arcface_train.py
    augment_face_folders.py
    export_embeddings.py
    recognize_face.py
  data/
    student_db_pg.py
    build_training_from_db.py
  pipeline/
    cli.py             # điều phối lệnh
    steps.py           # train-full nối 4 bước
```

## Đường dẫn mặc định

- **`REPO_ROOT`**: thư mục `modelcore/` (cha của `Model_v2/`)
- **`MODEL_DIR`**: thư mục `Model_v2/`
- **`TrainingSelected`**, **`TrainingAugmented`**: mặc định dưới `REPO_ROOT` (cạnh `Model_v2/`)
- **`arcface_runs/`**, weight YOLO: dưới `Model_v2/` (và `Model_v2/detect_tracking/` cho file `.pt`)

```bash
cd modelcore/Model_v2
python -m face_pipeline check-db
python -m face_pipeline check-db --db-host 127.0.0.1 --db-password 1234
```

### PostgreSQL (webcam track + điểm danh)

Điểm danh từ **`track`** ghi vào bảng **`yolo_face_attendance`** (không dùng `attendance_records` nếu bảng đó thuộc app khác / có `session_id`…).

Mặc định kết nối: `localhost:5432`, database `face_attendance_db`, user `postgres`, mật khẩu từ `FACE_ATTENDANCE_PG_PASSWORD` hoặc `1234`; ghi đè bằng `--pg-*` khi chạy `track`.
Cấu hình dùng chung nằm trong `face_pipeline/data/pg_settings.py` (`DEFAULT_PG_*`, `connect_pg()`).

## Shim (tương thích)

Ví dụ vẫn chạy được (khi đang ở thư mục `modelcore/Model_v2`):

```bash
python arcface_train.py --help
python yolov8_face_track_webcam.py --help
```

(chúng import vào `face_pipeline.*`).
