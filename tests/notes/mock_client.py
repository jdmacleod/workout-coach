from coach.notes.client import NotesClient
from coach.notes.exceptions import NoteNotFoundError


class MockNotesClient(NotesClient):
    """In-memory mock for testing. Stores notes in a dict."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def create_note(self, folder: str, title: str, body: str) -> None:
        self._store[(folder, title)] = body

    def get_note(self, folder: str, title: str) -> str:
        key = (folder, title)
        if key not in self._store:
            raise NoteNotFoundError(title)
        return self._store[key]

    def update_note(self, folder: str, title: str, body: str) -> None:
        self._store[(folder, title)] = body

    def note_exists(self, folder: str, title: str) -> bool:
        return (folder, title) in self._store

    def list_notes(self, folder: str) -> list[str]:
        return [t for (f, t) in self._store if f == folder]

    def ensure_folder(self, folder_path: str) -> None:
        pass  # no-op in tests

    def delete_note(self, folder: str, title: str) -> None:
        key = (folder, title)
        if key not in self._store:
            raise NoteNotFoundError(title)
        del self._store[key]
