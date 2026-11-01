# Foundation test-data provenance

All test inputs are authored synthetic infrastructure values: dummy UUIDs, role strings, loopback/invalid origins, deliberately invalid configuration, and private-marker strings used to detect accidental logging. No patient readings, meal images, insulin histories, personal identifiers, records, research datasets or fixture payload files are used. Inline fixture values must not be replaced with real data. pytest tests rejection, lifecycle, privacy-redacted logging/errors, generated contracts and Git inclusion safeguards; frontend DOM tests live beside the components/client under `apps/web/src`.

Future clinical-feature tests require separately documented synthetic fixtures plus unit, integration and safety regression coverage under the repository rules. Current engineering tests establish no clinical validity.
