-- 006_geography_seed.sql
-- Seed Australian state/territory dimension data

INSERT INTO dim_geography (geo_code, geo_name, geo_level, state)
VALUES
    ('1', 'New South Wales', 'state', 'NSW'),
    ('2', 'Victoria', 'state', 'VIC'),
    ('3', 'Queensland', 'state', 'QLD'),
    ('4', 'South Australia', 'state', 'SA'),
    ('5', 'Western Australia', 'state', 'WA'),
    ('6', 'Tasmania', 'state', 'TAS'),
    ('7', 'Northern Territory', 'state', 'NT'),
    ('8', 'Australian Capital Territory', 'state', 'ACT')
ON CONFLICT (geo_code, geo_level) DO NOTHING;
