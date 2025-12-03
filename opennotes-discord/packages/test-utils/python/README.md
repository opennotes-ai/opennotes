# Open Notes Test Utils (Python)

Shared testing utilities and fixtures for Open Notes Python services.

## Installation

```bash
# Install from local package
uv pip install -e /path/to/packages/test-utils/python
```

## Usage

### Fixtures

```python
from opennotes_test_utils import sample_participant_ids, test_user_data

# Use standard participant IDs in tests
participant_ids = sample_participant_ids()
assert participant_ids["author1"] == "author_participant_1"

# Use standard test user data
user_data = test_user_data()
assert user_data["username"] == "testuser"
```

### In pytest

```python
import pytest
from opennotes_test_utils import sample_participant_ids, test_user_data

@pytest.fixture
def participants():
    return sample_participant_ids()

@pytest.fixture
def test_user():
    return test_user_data()

def test_scoring(participants):
    # Use participant IDs in your test
    assert participants["rater1"] == "rater_participant_1"
```

## Available Fixtures

### sample_participant_ids()

Returns standard test participant IDs for scoring tests:

- `author1`, `author2`: Note authors
- `rater1`, `rater2`, `rater3`: Note raters

### test_user_data()

Returns standard test user data for authentication tests:

- `username`: testuser
- `email`: test@example.com
- `password`: testpassword123
- `full_name`: Test User
