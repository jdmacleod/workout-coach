from coach.notes.client import NotesClient, _strip_html
from coach.notes.exceptions import NoteNotFoundError


class MockNotesClient(NotesClient):
    """In-memory mock for testing. Stores notes in a dict.

    get_note applies _strip_html() on return to match the real NotesClient, which
    always strips the HTML that Apple Notes returns. This means tests can write HTML
    notes and read back plaintext (with semantic tags converted to Markdown equivalents).

    create_note returns a fake x-coredata xcid ("x-coredata://mock/ICNote/pN") so that
    callers that build note_urls from xcids work correctly in tests.
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}
        self._xcids: dict[tuple[str, str], str] = {}
        self._next_id: int = 1

    def create_note(self, folder: str, title: str, body: str) -> str | None:
        key = (folder, title)
        self._store[key] = body
        xcid = f"x-coredata://mock/ICNote/p{self._next_id}"
        self._xcids[key] = xcid
        self._next_id += 1
        return xcid

    def get_note_id(self, folder: str, title: str) -> str | None:
        return self._xcids.get((folder, title))

    def get_note(self, folder: str, title: str) -> str:
        key = (folder, title)
        if key not in self._store:
            raise NoteNotFoundError(title)
        return _strip_html(self._store[key])

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
