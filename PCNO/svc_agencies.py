import UTILS as u
import numpy as np
import pandas as pd
import COMPARE_ADDRESSES as ca


DEDUPED = '../../../rcc-uchicago/PCNO/CSV/chicago/2018-07-03_link_agencies_output.csv'
HQ = '../../../rcc-uchicago/PCNO/CSV/chicago/contracts_w_hq_addresses.csv'
SVC = '../../../rcc-uchicago/PCNO/CSV/chicago/service_agencies.csv'

THRESH = 0.34


def linker():
    '''
    '''

    link = read_deduplicated()
    link1 = link.rename(columns={'VendorName':'VendorName_LINK1'},index=str)
    link2 = u.rename_cols(link,['VendorName','CSDS_Vendor_ID'],'_LINK2')

    df = link1.merge(link2,how='left')
    df = df[df['CSDS_Vendor_ID'] != df['CSDS_Vendor_ID_LINK2']].reset_index(drop=True)

    return df


def merger():
    '''
    '''

    link = linker()
    hq = read_hq()
    svc = read_svc()

    merged = hq.merge(link,how='left').merge(svc,how='left')

    return merged


def dollars_per_location():
    '''
    '''

    link = linker()
    svc = read_svc()
    hq = read_hq()[['CSDS_Vendor_ID','VendorName','Agency_Summed_Amount']].drop_duplicates()

    merged = hq.merge(link,how='left').merge(svc,how='inner')

    merged = merged.assign(Dollars_Per_Location=merged['Agency_Summed_Amount']\
                           / merged['Num_Svc_Locations'])

    return merged.reset_index(drop=True)


def read_hq():
    '''
    '''

    df = pd.read_csv(HQ,converters={'Zip':str})
    agg_amounts = agg_funds(df)
    merged = df.merge(agg_amounts)

    return merged


def read_svc():
    '''
    '''

    print('\nReading in service agencies')

    df = pd.read_csv(SVC,converters={'ZipCode':str})
    df = u.rename_cols(df,[x for x in df.columns if x != 'CSDS_Svc_ID'],'_SVC')
    df = df.rename(columns={'CSDS_Svc_ID':'CSDS_Vendor_ID_LINK2'},index=str)

    key = 'CSDS_Vendor_ID_LINK2'
    target = 'Address_SVC'
    fixed_addresses = ca.fix_duplicate_addresses(df,key,target)
    fixed_addresses = fixed_addresses.drop_duplicates(subset=[key,target])

    counts = count_svc_addr(fixed_addresses)
    merged = fixed_addresses.merge(counts)

    return merged.reset_index(drop=True)


def read_deduplicated():
    '''
    '''

    df = pd.read_csv(DEDUPED,converters={'ClusterID':str})

    df = df[df['LinkScore'] >= THRESH]

    df = df.drop(['LinkScore','SourceFile'],axis=1)

    return df


def agg_funds(hq):
    '''
    '''

    agg = hq.groupby('CSDS_Vendor_ID')['Amount'].sum().reset_index()
    agg = agg.rename(columns={'Amount':'Agency_Summed_Amount'},index=str)

    return agg


def count_svc_addr(df):
    '''
    '''

    #counts = df.groupby('ClusterID')['CSDS_Vendor_ID_LINK2'].value_counts()
    df = df.assign(Constant=1)
    counts = df.groupby('CSDS_Vendor_ID_LINK2')['Constant'].count()
    counts.name = 'Num_Svc_Locations'

    return counts.to_frame().reset_index()


def needs_geocoding(df,id,lat,lon,address_fields):
    '''
    '''

    #address,city,state,zipcode = address_fields

    needs_geo = df[[id,lat,lon, x for x in address_fields]].drop_duplicates()
    needs_geo = needs_geo[pd.isnull(needs_geo[lat,lon])]
    needs_geo = needs_geo.drop([lat,lon],axis=1)

    new_cols = [re.sub('_SVC$','',x) for x in needs_geo.columns]
    cn = dict(zip(needs_geo.columns,new_cols))

    needs_geo = needs_geo.rename(columns=cn,index=str)
    needs_geo = needs_geo.rename(columns={'ZipCode':'Zip'},index=str)

    return needs_geo.reset_index(drop=True)



if __name__ == '__main__':

    print()
    #merged = merger()
    dollars_div = dollars_per_location()
    dollars_div.to_csv('../../../rcc-uchicago/PCNO/CSV/chicago/dollars_div.csv',index=False)

    lat = 'Latitude_SVC'
    lon = 'Longitude_SVC'
    id_col =






    '''
    $/agency @ service addresses

    CONTRACTAGENCIES [VendorName] LINK [Name] SERVICEAGENCIES

    -Count the number of service addresses per agency; add as a column
    -Add agg_dollars as a column
    -Divide agg_dollars by num_locations















    *******
    Problem:  Single locations are defined by multiple unique address strings, all the cleaning notwithstanding
    *******
    Options:
    -Geocode everything, then do float comparisons on the coordinates (or drop some that are within some tolerance of others)
    -Split up addresses with re and try to compare them
    -Split up addresses with the Usaddress library and try to compare them
    -Deduplicate with Logan's module (concatenate all to a single field first)
    -Deduplicate with the Dedupe library (I'll need to write a script that requires the CSDS_Agency_ID to match)
    '''
