"""Private local storage for uploaded essay originals."""

import os
from pathlib import Path, PurePosixPath
from uuid import UUID


class StorageError(OSError):
    """Raised when an essay file cannot be safely stored or removed."""


class LocalEssayStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def save(self, *, essay_id: UUID, extension: str, data: bytes) -> str:
        relative_path = PurePosixPath("essays") / f"{essay_id.hex}{extension}"
        destination: Path | None = None
        created = False
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            parent = self.root / "essays"
            parent.mkdir(mode=0o700, exist_ok=True)
            resolved_parent = parent.resolve()
            resolved_parent.relative_to(self.root)
            destination = resolved_parent / relative_path.name
            destination.relative_to(self.root)

            descriptor = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            created = True
            with os.fdopen(descriptor, "wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
        except (OSError, ValueError) as exc:
            try:
                if created and destination is not None:
                    destination.unlink(missing_ok=True)
            except OSError as cleanup_error:
                raise StorageError(
                    "The stored upload could not be safely cleaned up."
                ) from cleanup_error
            raise StorageError("The upload could not be stored.") from exc

        return relative_path.as_posix()

    def remove(self, relative_path: str) -> None:
        path = PurePosixPath(relative_path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not path.parts
            or "\\" in relative_path
            or ":" in relative_path
        ):
            raise StorageError("The stored file path is invalid.")

        target = self.root.joinpath(*path.parts)
        try:
            target.resolve(strict=False).relative_to(self.root)
            target.unlink(missing_ok=True)
        except (OSError, ValueError) as exc:
            raise StorageError("The stored file could not be removed.") from exc
