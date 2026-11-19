"""Read the 14-column, headerless weather location list bundled in 中育管控桌面."""
import csv

COLUMNS = (
    'location_id', 'location_en', 'location_zh', 'country_code', 'country_en',
    'country_zh', 'province_en', 'province_zh', 'city_en', 'city_zh',
    'time_zone', 'latitude', 'longitude', 'administrative_code',
)


def read_locations(path):
    with path.open(encoding='utf-8-sig', newline='') as source:
        records = []
        for line, row in enumerate(csv.reader(source), 1):
            if len(row) != len(COLUMNS):
                raise ValueError(f'line {line} has {len(row)} fields, expected {len(COLUMNS)}')
            records.append(dict(zip(COLUMNS, row)))
        return records
