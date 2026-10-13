# Sports Complex Voice Agent

## Vapi tool API security

The `/tools/rate`, `/tools/availability`, and `/tools/book` endpoints require
`Authorization: Bearer <VAPI_TOOL_SECRET>`. Set `VAPI_TOOL_SECRET` in the local
`.env` file. The API fails closed with HTTP 503 if it is missing and returns
HTTP 401 for an absent or invalid token. Keep `.env` out of source control.

In Vapi, create a Custom Credential using that token in the `Authorization`
header with the Bearer prefix, then attach it to each API Request tool that
calls a protected endpoint.

## Reservation source of truth

MySQL is the source of truth for reservations. Availability checks read
confirmed MySQL bookings and do not access Google Calendar. Calendar events
are created as a view of successfully persisted bookings; Calendar-only events
are not imported or treated as reservations.

## Booking tool result contract

The booking tool response distinguishes:

- `booking_confirmed` and `booking_persisted`: true only after the database
  commit succeeds. `booking_persisted` is `null` if the commit result is
  ambiguous; in that case, do not retry automatically and ask staff to verify.
- `calendar_event_created`: whether Calendar creation was confirmed. It can be
  `null` if Calendar returned an ambiguous error.
- `email_sent`: whether the confirmation-email sender accepted the message.

The assistant should announce a booking only when `booking_confirmed` is true,
and separately report when `email_sent` is false. An unavailable slot must
not be booked.
