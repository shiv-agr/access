import pandas as pd
import numpy as np
import geopandas as gpd
from shapely.geometry import Point
import matplotlib.patches as mpatches

from matplotlib import mlab
import matplotlib as mpl
from p2p import TransitMatrix
import os.path, csv, math, sys, logging, json, time
import copy

class ModelData(object):
    '''
    A parent class to hold/process data for more advanced geospatial
    models like HSSAModel and PCSpendModel. The 'upper' argument in
    the __init__ is the time (in minutes), above which a source and dest
    are considered to be out of range of each other.
    '''

    def __init__(self, network_type, upper):
        self.network_type = network_type
        self.sp_matrix = None
        self.dests = None
        self.sources = None
        self.category_set = None
        self.source2dest = {}
        self.dest2source = {}
        self.dest2cats = {}
        self.cat2dests = {}
        self.near_nbr = {}
        self.n_dests_in_range = {}
        self.time = {}
        self.time_val2 = {}
        self.use_n_nearest = 10

        self.sources_nn = {}
        self.idx_2_col = {}

        self.source_id_list = []
        self.dest_id_list = []

        self.sp_matrix_good = False
        self.dests_good = False
        self.sources_good = False
        self.processed_good = False

        self.primary_hints = None
        self.secondary_hints = None

        assert network_type in ['drive', 'walk', 'bike'], 'gave invalid mode of transit. Must be one of: drive, walk, bike'
        self.upper = upper * 60 #convert minutes from input to seconds

        self.set_logging('info')


        self.valid_population = True
        self.valid_target = True
        self.valid_category = True
        self.valid_lower_areal_unit = True


    def get_time(self, source, dest):
        '''
        Return the time, in seconds, from source to dest.
        '''
        assert self.sp_matrix_good, 'load shortest path matrix before this step'

        time = self.sp_matrix.get(source, dest)

        return time


    def get_population(self, source_id):
        '''
        Return the population at a source point.
        '''
        assert self.sources_good, 'load sources before this step'

        return self.sources.loc[source_id, 'population']

    def get_target(self, dest_id):
        '''
        Return the target value at a dest point.
        '''
        assert self.dests_good, 'load dests before this step'

        return self.dests.loc[dest_id, 'target']


    def get_category(self, dest_id):
        '''
        Return the category of a dest point.
        '''
        assert self.dests_good, 'load dests before this step'

        return str(self.dest2cats[dest_id])


    def figure_name(self):
        '''
        Return a unique figure name.
        '''
        i = 0
        if not os.path.exists("figures/"):
            os.makedirs("figures/")
        fig_name = 'figures/fig_0.png'
        while (os.path.isfile(fig_name)):
            i += 1
            fig_name = 'figures/fig_{}.png'.format(i)

        return fig_name


    def process(self):
        '''
        Generate mappings for the model to ugse.
        '''

        #need to make sure we've loaded these data first
        assert self.sp_matrix_good, 'load shortest path matrix before this step'
        assert self.sources_good, 'load sources before this step'
        assert self.dests_good, 'load destinations before this step'
        self.logger.info('Processing... This could take a while')

        #Calculate time to nearest neighbor (near_nbr) and number of destinations within buffer (n_dests_in_range) metrics.
        #pre map dest->category
        start_time = time.time()
        CAT = self.dests.columns.get_loc('category') + 1
        ID = 0
        rv = {}
        included_cats = set()
        nearest_cat_template = {}
        n_dests_in_range_template = {}
        for data in self.dests.itertuples():
            self.dest2cats[data[ID]] = str(data[CAT])
            if str(data[CAT]) in included_cats:
                self.cat2dests[data[CAT]].append(data[ID])
            else:
                self.cat2dests[str(data[CAT])] = [data[ID]]
                included_cats.add(data[CAT])
                nearest_cat_template[data[CAT]] = None
                n_dests_in_range_template[data[CAT]] = 0


        #pre map sources->dests (in range) and dests->sources (in range)
        already_added_a = set()
        already_added_b = set()
        near_nbr = {}
        n_dests_in_range = {}
        time_val2 = {}
        time_val={}

        for source_id in self.source_id_list:
            near_nbr[source_id] = copy.deepcopy(nearest_cat_template)
            n_dests_in_range[source_id] = copy.deepcopy(n_dests_in_range_template)
            for dest_id in self.dest_id_list:
                time_val = self.get_time(source_id, dest_id)
                cat = self.get_category(dest_id)
                self.time_val = self.get_time(source_id, dest_id)
                self.time_val2[source_id] = self.get_time(source_id, dest_id)

                #update the closest dest for each category of this source.
                #Specify non negative values in order to disregard epsilon values.
                if time_val>=0:
                    if near_nbr[source_id][cat] is None:
                        near_nbr[source_id][cat] = time_val
                    elif time_val < near_nbr[source_id][cat]:
                        near_nbr[source_id][cat] = time_val

                #Within upper limit buffer range (default is 30 minutes.)
                if time_val <= self.upper and time_val>=0:
                    #increment the number of destinations in range of this source
                    n_dests_in_range[source_id][cat] += 1

                    if source_id in already_added_a:
                        self.source2dest[source_id].append((dest_id, time_val))
                    else:
                        self.source2dest[source_id] = [(dest_id,time_val)]
                        already_added_a.add(source_id)
                    if dest_id in already_added_b:
                        self.dest2source[dest_id].append((source_id, time_val))
                    else:
                        self.dest2source[dest_id] = [(source_id, time_val)]
                        already_added_b.add(dest_id)
                
        #convert dictionaries to dataframes
        self.near_nbr = pd.DataFrame.from_dict(near_nbr, 
            orient='index')

        self.n_dests_in_range = pd.DataFrame.from_dict(n_dests_in_range, 
            orient='index')

        self.time_val2 = pd.DataFrame.from_dict(self.time_val2, orient='index')

        #Rename column to 'time'
        self.time_val2=self.time_val2.rename(columns={0:'time'})

        #Find list within matrix with negative values.
        #When constructing the matrix with p2p, the negative values (-999) are the edges on the border of the bounding box.
        list_id=self.time_val2.index[self.time_val2['time'] <0].tolist()

        #In final output of metrics, drop the negative values of time distance travel matrix
        for i in list_id:
            for j in self.n_dests_in_range.keys():
                self.n_dests_in_range.at[i,j] = -9999
        self.n_dests_in_range=self.n_dests_in_range.replace(-9999, np.nan)

        for i in list_id:
            for j in self.near_nbr.keys():
                self.near_nbr.at[i,j] = -9999
        self.near_nbr=self.near_nbr.replace(-9999, np.nan)

        #Get nearest neighbor facility in minutes
        self.near_nbr =self.near_nbr/60

        self.processed_good = True
        self.logger.info('Finished processing ModelData in {:,.2f} seconds'.format(time.time() - start_time))


    def plot_nearest_providers(self, limit_categories=None, 
        title='Closest Point CDF', n_bins=500, resolution='block'):
        '''
        Plot a cdf of travel times to the closest provider
        for each category.
        '''

        assert resolution in ['block', 'population'], 'must use block or resolution'
        #assert resolution != 'population', 'this feature is a Work in Progress'
        assert type(limit_categories) in [type(set()), type([]), type(None)], 'limit_categories must be type list, set or None'

        figure_name = self.figure_name()

        
        #initialize block parameters
        mpl.pyplot.close()
        mpl.pyplot.rcParams['axes.facecolor'] = '#cfcfd1'
        fig, ax = mpl.pyplot.subplots(figsize=(8, 4))

        available_colors = ['black','magenta','lime','red','black','orange','grey','yellow','brown','teal']
        color_keys = []
        if self.limit_categories:
            for category in self.limit_categories:
                self.near_nbr[category][self.near_nbr[category] > self.upper] = self.upper
                x = self.near_nbr[category]
                #Drop any NaNs to avoid error in plotting 
                x=x.dropna()
                color = available_colors.pop(0)
                patch = mpatches.Patch(color=color, label=category)
                color_keys.append(patch)
                if resolution == 'population':
                    res = {}
                    for block_id, time_val in x.iteritems():
                        block_pop = self.get_population(block_id)
                        if block_pop <= 0:
                            continue
                        for i in range(block_pop):
                            temp_id = '{}_{}'.format(block_id, i)
                            res[temp_id] = time_val
                    res = pd.Series(data=res)
                    n, bins, blah = ax.hist(res, n_bins, density=True, histtype='step',
                    cumulative=True, label=category, color=color)
                else:
                    n, bins, blah = ax.hist(x, n_bins, density=True, histtype='step',
                    cumulative=True, label=category, color=color)

        else:
            for category in self.category_set:
                self.near_nbr[category][self.near_nbr[category] > self.upper] = self.upper
                x = self.near_nbr[category]
                #Drop any NaNs to avoid error in plotting 
                x=x.dropna()
                color = available_colors.pop(0)
                patch = mpatches.Patch(color=color, label=category)
                color_keys.append(patch)
                if resolution == 'population':
                    res = {}
                    for block_id, time_val in x.iteritems():
                        block_pop = self.get_population(block_id)
                        if block_pop <= 0:
                            continue
                        for i in range(block_pop):
                            temp_id = '{}_{}'.format(block_id, i)
                            res[temp_id] = time_val
                    res = pd.Series(data=res)
                    n, bins, blah = ax.hist(res, n_bins, density=True, histtype='step',
                    cumulative=True, label=category, color=color)
                else:
                    n, bins, blah = ax.hist(x, n_bins, density=True, histtype='step',
                    cumulative=True, label=category, color=color)

        if self.limit_categories:
            ax.legend(loc='best',handles=color_keys)
        else:
            ax.legend(loc='best', handles=color_keys)
        ax.grid(True)
        ax.set_title(title)
        ax.set_xlabel('Time in seconds')
        ax.set_ylabel('Percent of {} Within Range'.format(resolution))
        fig_name = self.figure_name()
        mpl.pyplot.savefig(fig_name, dpi=400)
        mpl.pyplot.show()
        self.logger.info('Plot was saved to: {}'.format(fig_name))


    def get_output_filename(self, keyword, extension='csv', file_path='data/'):
        '''
        Given a keyword, find an unused filename.
        '''
        
        if not os.path.exists(file_path):
            os.makedirs(file_path)
        filename = file_path + '{}_0.{}'.format(keyword, extension)
        counter = 1
        while os.path.isfile(filename):
            filename = file_path + '{}_{}.{}'.format(keyword, counter, extension)
            counter += 1

        return filename


    def set_logging(self, level=None):
        '''
        Set the logging level to debug or info
        '''
        if not level:
            return

        if level == 'debug':
            logging.basicConfig(level=logging.DEBUG)
        elif level == 'info':
            logging.basicConfig(level=logging.INFO)
        else:
            return
        self.logger = logging.getLogger(__name__)


    def load_sp_matrix(self, filename=None):
        '''
        Load the shortest path matrix; if a filename is supplied,
        ModelData will attempt to load from file.
        If filename is not supplied, ModelData will generate
        a shortest path matrix using p2p (must be installed).
        '''

        #try to load from file if given
        if filename:
            self.sp_matrix = TransitMatrix(network_type=self.network_type, 
                read_from_file=filename)
            self.sp_matrix.process()
            self.logger.info('Loaded sp matrix from file: {}'.format(filename))
        else:
            assert self.sources_good, 'load sources before this step'
            assert self.dests_good, 'load destinations before this step'
            
            self.sp_matrix = TransitMatrix(network_type=self.network_type,
                primary_input=self.source_filename,
                secondary_input=self.dest_filename,
                write_to_file=True, load_to_mem=True, 
                primary_hints=self.primary_hints, 
                secondary_hints=self.secondary_hints)

            sl_file = None

            #need to load up speed limit table
            if self.network_type == 'drive':
                sl_file = 'BAH'
                while not os.path.isfile(sl_file):
                    sl_file = input('Please enter the filename of the speed limit table: ')
            self.sp_matrix.process(speed_limit_filename=sl_file)

            self.logger.info('Generated sp matrix to file: {}'.format(self.sp_matrix.output_filename))

        self.sp_matrix_good = True


    def load_sources_nn(self, use_n_nearest=10 ,filename='data/sources_nn_0.json'):
        '''
        This method will probably be deleted
        '''
    
        start = time.time()
        self.use_n_nearest = use_n_nearest
        if filename:
            self.sources_nn = json.load(open(filename))
            self.logger.info('loaded source nn data from file')
        else:
            assert self.sources_good, 'Load sources first'
            output_filename = self.get_output_filename('sources_nn', 'json')
            if self.network_type == 'drive':
                sl_file = 'BAH'
                while not os.path.isfile(sl_file):
                    sl_file = input('Please enter the filename of the speed limit table: ')
            else:
                sl_file = None

            tm = TransitMatrix(network_type=self.network_type, 
                primary_input=self.source_filename, 
                secondary_input=self.source_filename, output_type='json', 
                n_best_matches=use_n_nearest, epsilon=0.05)
            tm.process(speed_limit_filename=sl_file, output_filename=output_filename)

            self.sources_nn = json.load(open(output_filename))
            self.logger.info('Generated source relational data to file {}'.format(output_filename))


    def load_sources(self, filename=None, 
                     shapefile='resources/chi_comm_boundaries'):
        '''
        Load the source points for the model (from csv).
        For each point, the table should contain:
            -unique identifier (integer or string)
            -population (integer)
        '''
        #try to load the source table
        try:
            self.sources = pd.read_csv(filename)
        except:
            self.logger.error('Unable to load sources file: {}'.format(filename))
            sys.exit(0)
        
        #extract the column names from the table
        population = ''
        lower_areal_unit = ''
        idx = ''
        lat = ''
        lon = ''
        source_data_columns = self.sources.columns.values
        print('The variables in your data set are:')
        for var in source_data_columns:
            print('> ',var)
        while idx not in source_data_columns:
            idx = input('Enter the unique index variable: ')
        print('If you have no population variable, write "skip" (no quotations)')
        while population not in source_data_columns and population != 'skip':
            population = input('Enter the population variable: ')
        print('If you have no lower areal unit variable, write "skip" (no quotations)')
        while lower_areal_unit not in source_data_columns and lower_areal_unit != 'skip':
            lower_areal_unit = input('Enter the lower areal unit variable: ')
        while lat not in source_data_columns:
            lat = input('Enter the latitude variable: ')
        while lon not in source_data_columns:
            lon = input('Enter the longitude variable: ')

        #insert filler values for the population column if 
        #user does not want to include it
        if population == 'skip':
            self.sources['population'] = 1
            self.valid_population = False
            
        #insert filler values for the lower_areal_unit column if 
        #user lower_areal_unit not want to include it
        if population == 'skip':
            self.sources['lower_areal_unit'] = 1
            self.valid_lower_areal_unit = False

        #store the col names for later use
        self.primary_hints = {'xcol':lat, 'ycol':lon,'idx':idx}

        #rename columns, clean the data frame
        if population == 'skip':
            rename_cols = {lat:'lat', lon:'lon'}
        else:
            rename_cols = {population:'population', lat:'lat', lon:'lon', lower_areal_unit:'lower_areal_unit'}
  
        self.sources = pd.read_csv(filename)
        self.sources.set_index(idx, inplace=True)
        self.sources.rename(columns=rename_cols,inplace=True)
        self.sources = self.sources.reindex(columns=['lat','lon','population', 'lower_areal_unit'])

        #Disregard shapefile input to avoid spatial joins and potential calculation errors.
        #join source table with shapefile
        #copy = self.sources.copy(deep=True)
        #geometry = [Point(xy) for xy in zip(copy['lon'], copy['lat'])]
        #crs = {'init':'epsg:4326'}
        #copy = self.sources.copy(deep=True)
        #geo_sources = gpd.GeoDataFrame(copy, crs=crs, geometry=geometry)
        #boundaries_gdf = gpd.read_file(shapefile)
        #geo_sources = gpd.sjoin(boundaries_gdf, geo_sources, how='inner', 
        #                            op='intersects')
        #geo_sources.set_index('index_right', inplace=True)
        #self.sources = geo_sources[['community','population','lat','lon','geometry']]
        
        self.source_id_list = self.sources.index
        self.sources_good = True
        self.source_filename = filename


    def load_dests(self, filename=None, 
        shapefile='resources/chi_comm_boundaries', subset=None):
        '''
        Load the destination points for the model (from csv).
        For each point, the table should contain:
            -unique identifier (integer or string)
            -target value (integer or float)
            -category (string)
        '''

        #try to load dest file
        try:
            self.dests = pd.read_csv(filename)
        except:
            self.logger.error('Unable to load dest file: {}'.format(filename))
            sys.exit(0)

        #extract column names
        category = ''
        target = ''
        lower_areal_unit = ''
        idx = ''
        lat = ''
        lon = ''
        dest_data_columns = self.dests.columns.values
        print('The variables in your data set are:')
        for var in dest_data_columns:
            print('> ',var)
        while idx not in dest_data_columns:
            idx = input('Enter the unique index variable: ')
        print('If you have no target variable, write "skip" (no quotations)')
        while target not in dest_data_columns and target != 'skip':
            target = input('Enter the target variable: ')
        print('If you have no lower areal unit variable, write "skip" (no quotations)')
        while lower_areal_unit not in dest_data_columns and lower_areal_unit != 'skip':
            lower_areal_unit = input('Enter the lower areal unit variable: ')
        print('If you have no category variable, write "skip" (no quotations)')
        while category not in dest_data_columns and category != 'skip':
            category = input('Enter the category variable: ')
        while lat not in dest_data_columns:
            lat = input('Enter the latitude variable: ')
        while lon not in dest_data_columns:
            lon = input('Enter the longitude variable: ')

        #store the col names for later use
        self.secondary_hints = {'xcol':lat, 'ycol':lon,'idx':idx}

        if target == 'skip':
            target_name = 'target'
        else:
            target_name = target

        if category == 'skip':
            category_name = 'category'
        else:
            category_name = category

        if lower_areal_unit == 'skip':
            lower_areal_unit_name = 'lower_areal_unit'
        else:
            lower_areal_unit_name = lower_areal_unit

        self.dests = self.dests.reindex(columns=[idx, target_name, category_name, lat, lon, lower_areal_unit])
        #clean the table
        rename_cols = {target:'target', category:'category', lat:'lat', 
                       lon:'lon', lower_areal_unit: 'lower_areal_unit'}
        self.dests.set_index(idx, inplace=True)
        self.dests.rename(columns=rename_cols,inplace=True)
        if category == 'skip':
            self.dests['category'] = "CAT_UNDEFINED"
            self.valid_category = False
        if target == 'skip':
            self.valid_target = False
        if lower_areal_unit == 'skip':
            self.valid_lower_areal_unit = False
        if subset:
            self.dests = self.dests[self.dests['category'].isin(subset)]
        self.category_set = set()

        self.dests['category'].apply(str)
        self.category_set = set(self.dests['category'])

        #Disregard shapefile input to avoid spatial joins and potential calculation errors.
        #join dest table with shapefile
        #copy = self.dests.copy(deep=True)
        #geometry = [Point(xy) for xy in zip(copy['lon'], copy['lat'])]
        #crs = {'init':'epsg:4326'}
        #geo_dests = gpd.GeoDataFrame(copy, crs=crs, geometry=geometry)
        #boundaries_gdf = gpd.read_file(shapefile)
        #geo_dests = gpd.sjoin(boundaries_gdf, geo_dests, how='inner', op='intersects')
        #geo_dests.set_index('index_right', inplace=True)
        #self.dests = geo_dests[['category','lat','lon','target','community',]]

        self.dest_id_list = self.dests.index
        self.dests_good = True
        self.dest_filename = filename
