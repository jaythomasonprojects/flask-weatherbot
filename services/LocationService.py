from peewee import DoesNotExist
from fuzzywuzzy import process
from models import Location
import config
from utils import *

class LocationService:
    GOOGLE_KEY = config.GOOGLE_API_KEY
    GOOGLE_MAPS_API_URL = 'https://maps.googleapis.com/maps/api/geocode/json?address={}&key={}'

    @staticmethod
    def get_location_from_db(location_name):
        try:
            location = Location.get(Location.name == location_name)
            return location
        except DoesNotExist:
            return None

    @staticmethod
    def get_best_location_match(location_name, response):
        results = response['results']
        
        if len(results) == 1:
            return results[0]
        else:
            # Create a list of all the result's addresses
            response_names = [result['formatted_address'] for result in results]

            # Use Levenshtein distance to find the best match
            best_match = process.extractOne(location_name, response_names)

            # Return the API response result that contains the best match
            return next((result for result in results if result['formatted_address'] == best_match[0]), None)

    @staticmethod
    def is_valid_location(response):
        '''
        The Geocoding API response organises address components in a certain order, 
        typically with the locality at the top and the country at the bottom (but, this order can vary). 
        This function determines if the specified location is not an unwanted type (eg. a country)
        '''
        address_components = response['address_components']
        address_component_types = [component['types'] for component in address_components]
        unwanted_types = ['administrative_area_level_1', 'country']

        # If there's less than two address components, it's probably an unwanted type
        if len(address_components) < 2:
            return False
        # Checks if the address type is not an unwanted type
        elif any(type in address_component_types for type in unwanted_types):
            return False
        else:
            return True
        
    @staticmethod
    def extract_location_data(location_data):
        province = None
        country = None
        
        for component in location_data['address_components']:
            if 'administrative_area_level_1' in component['types']:
                province = component['long_name']
            elif 'country' in component['types']:
                country = component['long_name']

        return {
            'name': location_data['address_components'][0]['long_name'],
            'province': province,
            'country': country,
            'latitude': location_data['geometry']['location']['lat'],
            'longitude': location_data['geometry']['location']['lng']
        }

    @staticmethod
    def get_location_from_api(location_name):
        url = LocationService.GOOGLE_MAPS_API_URL.format(location_name, LocationService.GOOGLE_KEY)
        response = make_request(url)
        
        if response['status'] != 'OK':
            console_log(f"Error fetching location data for '{location_name}'. API response: {response['status']}", "ERROR")
            return None
        else:
            location = LocationService.get_best_location_match(location_name, response)

            if location and LocationService.is_valid_location(location):
                return LocationService.extract_location_data(location)
            else:
                console_log(f"'{location_name}' is not a valid location (eg. a country).", "ERROR")
                return None

    @staticmethod
    def add_location_to_db(location_data):
        location = Location.create(
            name=location_data['name'],
            province=location_data['province'],
            country=location_data['country'],
            latitude=location_data['latitude'],
            longitude=location_data['longitude']
        )
        return location

    @staticmethod
    def fetch_location_data(location_name):
        # First, check if the location is already in the database
        location_from_db = LocationService.get_location_from_db(location_name)
        if location_from_db:
            console_log(f"Location '{location_name}' found in database.", "INFO")
            return location_from_db

        # Second, if the location is not in the database, fetch it from the API
        console_log(f"Location '{location_name}' not found in database. Fetching from API...", "INFO")
        location_from_api = LocationService.get_location_from_api(location_name)

        # If API call is unsuccessful, return None
        if not location_from_api:
            return None
        
        # If the API returns a different location name (eg. Stonehenge returns the town of Salisbury), check the database again to make sure it's not already there
        if location_from_api['name'] != location_name:
            console_log(f"API returned '{location_from_api['name']}' instead of '{location_name}'. Checking database for '{location_from_api['name']}'...", "INFO")
            location_from_db = LocationService.get_location_from_db(location_from_api['name'])
            if location_from_db:
                console_log(f"Location '{location_from_api['name']}' found in database.", "INFO")
                return location_from_db
        
        # If API call is successful, add the location data to the database and return it
        console_log(f"Location '{location_name}' found in API. Adding to database and returning...", "INFO")
        return LocationService.add_location_to_db(location_from_api)
