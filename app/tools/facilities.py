FACILITIES = {
    "tennis": "Tennis Court",
    "football": "Football Ground",
    "cricket": "Cricket Ground",
    "padel": "Padel Court",
}


def get_facility_name(facility: str) -> str | None:
    return FACILITIES.get(facility.strip().casefold())