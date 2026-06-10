class NotesClientError(Exception):
    """Base class for all Notes bridge errors."""


class NoteNotFoundError(NotesClientError):
    """Raised when a requested note does not exist."""


class FolderNotFoundError(NotesClientError):
    """Raised when a target folder does not exist."""


class NotesTimeoutError(NotesClientError):
    """Raised when an osascript call exceeds the timeout."""
