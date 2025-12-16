import re

NAME_REGEX = re.compile(r"^[A-Za-z0-9 ()_.-]{1,50}$")
NAME_ALLOWED_MESSAGE = (
    "must be 1-50 characters and may only contain letters, numbers, spaces, "
    "parentheses, periods, underscores, or hyphens."
)

