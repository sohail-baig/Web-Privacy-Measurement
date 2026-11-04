"""Student task: implement generic, local-only consent handling.

Search visible consent controls across frames using generic selectors/keywords.
Do not special-case university URLs or use online APIs, LLMs or extensions.
Return 'accepted', 'not_found', or 'failed'. Do not equate clicking with acceptance:
verify the dialog changed/disappeared. Keep screenshots when no dialog exists.
"""

IMPLEMENTED = False


def accept_consent(page):
    raise NotImplementedError('Implement generic consent detection in crawler_src/consent.py, then set IMPLEMENTED = True.')
