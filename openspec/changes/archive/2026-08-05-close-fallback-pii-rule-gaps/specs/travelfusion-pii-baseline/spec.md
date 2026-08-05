## ADDED Requirements

### Requirement: Travelfusion booking-profile leaves are reversibly encrypted
For `GetBookingDetails` and `GetLatestBookingDetails`, the Travelfusion baseline SHALL encrypt the
actual phone and fax leaf values, traveller age, title, DOB custom-parameter values, supported
passport and frequent-flyer custom-parameter values, and `ClientAddress` diagnostic values. It SHALL
not rewrite whitespace on complex phone container elements.

This coverage SHALL remain optional: none of these rules, including the existing traveller-name
anchor, is required to match.

#### Scenario: Phone leaves encrypt without mixed container text
- **WHEN** a booking profile contains home, work, mobile, or fax components
- **THEN** every populated component becomes an `ENC_` token, the container has no injected text,
  and de-anonymization restores the original component values

#### Scenario: Custom demographic and identity values encrypt
- **WHEN** a traveller custom parameter identifies DOB, passport, residence-country, or
  frequent-flyer data
- **THEN** its value becomes an `ENC_` token and round-trips to the original value

#### Scenario: Traveller demographic and client IP values encrypt
- **WHEN** a response carries traveller age/title or `GeneralInfoItem[Name='ClientAddress']/Value`
- **THEN** each value is encrypted and absent in plaintext from the redacted response
