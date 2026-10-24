import pandas as pd

df = pd.read_excel('data/cellplan/Cell_Plan_Data_21102026.xlsx')
df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')

print('Total rows:', len(df))
groups = df.groupby(['site_id', 'site_name'])
print('Number of sites:', len(groups))

# Show first site
for (sid, sname), cells in groups:
    print(f'\nSite {sid} ({sname}): {len(cells)} cells')
    print(cells[['cell_name', 'technology', 'frequency', 'band', 'azimuth']].head())
    break