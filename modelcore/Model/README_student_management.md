# Student Management with PostgreSQL

This guide adds student CRUD + face folder synchronization for your ArcFace pipeline.

## 1) Prerequisites

- PostgreSQL database is available (you can manage it in pgAdmin 4).
- Python package:

```bash
pip install psycopg2-binary
```

## 2) Initialize schema

```bash
python Model/student_db_pg.py \
  --db-host localhost \
  --db-port 5432 \
  --db-name your_db \
  --db-user your_user \
  --db-password your_password \
  --command init-schema
```

## 3) Add student

```bash
python Model/student_db_pg.py \
  --db-name your_db \
  --db-user your_user \
  --db-password your_password \
  --training-dir Training \
  --command add-student \
  --student-code SE12345 \
  --full-name "Nguyen Van A" \
  --class-code "INT1407_1" \
  --email "a@example.com" \
  --phone "0912345678" \
  --image "/absolute/path/to/face.jpg"
```

## 4) Update student

Update full name + status:

```bash
python Model/student_db_pg.py \
  --db-name your_db \
  --db-user your_user \
  --db-password your_password \
  --command update-student \
  --student-code SE12345 \
  --full-name "Nguyen Van A Updated" \
  --status active
```

Change student code (face folder will be renamed automatically):

```bash
python Model/student_db_pg.py \
  --db-name your_db \
  --db-user your_user \
  --db-password your_password \
  --command update-student \
  --student-code SE12345 \
  --new-student-code SE12345_NEW
```

## 5) Delete student

Soft delete (exclude from future training):

```bash
python Model/student_db_pg.py \
  --db-name your_db \
  --db-user your_user \
  --db-password your_password \
  --command soft-delete-student \
  --student-code SE12345
```

Hard delete + remove folder:

```bash
python Model/student_db_pg.py \
  --db-name your_db \
  --db-user your_user \
  --db-password your_password \
  --command hard-delete-student \
  --student-code SE12345 \
  --purge-face-folder
```

## 6) Build training dataset from DB

Build only active students:

```bash
python Model/build_training_from_db.py \
  --db-name your_db \
  --db-user your_user \
  --db-password your_password \
  --output-dir TrainingSelected \
  --overwrite
```

Build active students from one class:

```bash
python Model/build_training_from_db.py \
  --db-name your_db \
  --db-user your_user \
  --db-password your_password \
  --class-code INT1407_1 \
  --output-dir TrainingSelected \
  --overwrite
```

Then train:

```bash
python Model/arcface_train.py --training-dir TrainingSelected
```

## 7) Notes

- `status` values:
  - `active`: included in training
  - `inactive`: excluded
  - `out_of_class`: excluded
- Student folder naming is based on `student_code` to avoid conflicts when full name changes.
