def sample_participant_ids() -> dict[str, str]:
    """
    Standard test participant IDs for scoring tests.

    Returns a dictionary of participant IDs with clear role distinctions:
    - author1, author2: Note authors
    - rater1, rater2, rater3: Note raters
    """
    return {
        "author1": "author_participant_1",
        "author2": "author_participant_2",
        "rater1": "rater_participant_1",
        "rater2": "rater_participant_2",
        "rater3": "rater_participant_3",
    }


def test_user_data() -> dict[str, str]:
    """
    Standard test user data for authentication tests.

    Returns a dictionary with:
    - username: testuser
    - email: test@example.com
    - password: testpassword123
    - full_name: Test User
    """
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User",
    }
