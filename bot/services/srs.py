from bot import db


def process_answer(prog, correct, test_type, session_type="on_demand"):
    """Process a review answer and update the database."""
    db.update_progress(prog, correct, test_type, session_type=session_type)
