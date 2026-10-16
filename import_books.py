"""Import book covers from static/images and upsert the matching catalog data."""

from __future__ import annotations

import argparse
import random
import re
import shutil
import unicodedata
from pathlib import Path

from biblio import create_app
from biblio.extensions import db
from biblio.models import Book, Category


ROOT = Path(__file__).resolve().parent
IMAGE_ROOT = ROOT / "static" / "images"
DATABASE = ROOT / "biblio.db"
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_DESCRIPTION = "Đang cập nhật"
PLACEHOLDER_NAME = "placeholder.png"


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFD", value.lower())
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return value.replace("đ", "d")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize(value)).strip("-")


def filename_title(path: Path) -> str:
    stem = path.stem.replace("-", " ").replace("_", " ")
    return " ".join(stem.split()).strip()


def title_and_author(path: Path) -> tuple[str, str]:
    words = filename_title(path)
    if "_" in path.stem:
        title_part, author_part = path.stem.rsplit("_", 1)
        if title_part.strip() and author_part.strip():
            return (
                " ".join(title_part.replace("-", " ").split()).title(),
                " ".join(author_part.replace("-", " ").split()).title(),
            )
    return words, "Đang cập nhật"


def discover_images() -> list[Path]:
    return sorted(
        (
            path
            for path in IMAGE_ROOT.rglob("*")
            if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
        ),
        key=lambda path: path.as_posix().lower(),
    )


def relative_image_path(path: Path) -> str:
    return path.relative_to(IMAGE_ROOT).as_posix()


def image_exists(image: str | None) -> bool:
    if not image:
        return False
    old_path = IMAGE_ROOT / "books" / image
    new_path = IMAGE_ROOT / image
    return old_path.is_file() or new_path.is_file()


def backup_database() -> Path:
    backup = DATABASE.with_name(f"{DATABASE.stem}.backup-import{DATABASE.suffix}")
    shutil.copy2(DATABASE, backup)
    return backup


def print_report(report: dict) -> None:
    print("\n=== KẾT QUẢ IMPORT ẢNH SÁCH ===")
    print(f"Sách được gán ảnh mới: {report['assigned']}")
    print(f"Sách tạo mới: {report['created']}")
    print(f"Ảnh không khớp sách cũ: {len(report['unmatched'])}")
    for filename in report["unmatched"]:
        print(f"  - {filename}")
    print(f"Sách vẫn thiếu ảnh trước placeholder: {len(report['missing'])}")
    for title in report["missing"]:
        print(f"  - {title}")
    print(f"Placeholder sẽ được dùng cho: {report['placeholder_count']} sách")
    if report["dry_run"]:
        print("\nDRY-RUN: chưa ghi database, chưa tạo backup và chưa tạo placeholder.")


def run(dry_run: bool) -> None:
    app = create_app()
    with app.app_context():
        categories = {
            slugify(category.name): category for category in Category.query.all()
        }
        all_books = Book.query.all()
        books = {slugify(book.title): book for book in all_books}
        books_by_image = {
            slugify(Path(book.image).stem): book
            for book in all_books
            if book.image
        }
        projected_images: dict[int, str] = {
            book.id: book.image for book in Book.query.all() if image_exists(book.image)
        }
        report = {
            "assigned": 0,
            "created": 0,
            "unmatched": [],
            "missing": [],
            "placeholder_count": 0,
            "dry_run": dry_run,
        }
        pending_categories = []
        pending_books = []

        for image in discover_images():
            full_title = filename_title(image)
            book = books_by_image.get(slugify(image.stem)) or books.get(
                slugify(full_title)
            )
            if book is None:
                title, author = title_and_author(image)
            else:
                title, author = book.title, book.author
            category_key = slugify(image.parent.name)
            category = categories.get(category_key)
            if category is None:
                category = Category(name=image.parent.name)
                categories[category_key] = category
                pending_categories.append(category)

            book = books_by_image.get(slugify(image.stem)) or books.get(slugify(title))
            image_name = relative_image_path(image)
            if book is None:
                book = Book(
                    title=title,
                    author=author,
                    price=random.randrange(50000, 250001, 1000),
                    stock=20,
                    description=DEFAULT_DESCRIPTION,
                    image=image_name,
                    category=category,
                )
                books[slugify(title)] = book
                pending_books.append(book)
                report["created"] += 1
                report["unmatched"].append(image_name)
                if not dry_run:
                    db.session.add(book)
                continue

            if image_exists(book.image):
                projected_images[book.id] = book.image
                continue

            book.image = image_name
            projected_images[book.id] = image_name
            report["assigned"] += 1

        all_books = list(Book.query.all()) + pending_books
        report["missing"] = [
            book.title
            for book in all_books
            if book.id not in projected_images and not image_exists(book.image)
        ]
        report["placeholder_count"] = len(report["missing"])

        if not dry_run:
            backup = backup_database()
            for category in pending_categories:
                db.session.add(category)
            placeholder = IMAGE_ROOT / "books" / PLACEHOLDER_NAME
            if report["missing"]:
                placeholder.write_bytes(
                    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                    b"\x00\x00\x00\x0dIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f"
                    b"\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
                )
                for book in all_books:
                    if book.title in report["missing"]:
                        book.image = PLACEHOLDER_NAME
            db.session.commit()
            print(f"\nĐã sao lưu database tại: {backup}")

        print_report(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import ảnh bìa sách vào Biblio.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ xem trước thay đổi, không ghi database.",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)
