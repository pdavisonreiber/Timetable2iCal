import requests
import json
import os
import pytz
import datetime
from getpass import getpass
from ics import Calendar, Event
#from icalendar import Calendar, Event, vText, vDatetime
from requests_ntlm import HttpNtlmAuth
import xml.etree.ElementTree as ET
import progressbar
    
def date_range(json):
	date_range = []
	date = datetime.date.fromisoformat(json['start'])
	end = datetime.date.fromisoformat(json['end'])
	one_day = datetime.timedelta(days=1)
	
	while date <= end:
		date_range.append(date)
		date += one_day
	
	return date_range	

def merge(array_of_arrays):
	merged_array = []
	for array in array_of_arrays:
		for item in array:
			merged_array.append(item)
			
	return merged_array

def index(array, by, unique=False):
	indexed_items = {}
	
	if callable(by):
		key = by
	else:
		key = lambda item: item[by]
	
	if unique:
		for item in array:
			indexed_items[key(item)] = item
	else:
		for item in array:
			if key(item) not in indexed_items:
				indexed_items[key(item)] = []
			indexed_items[key(item)] += [item]
	
	return indexed_items

class TimetableManager:
	def __init__(self):
		self.calendar = Calendar()
		self.events = []
		
	def new_event(self, name, location, start, end, uid):
		event = Event()
		event.name = name
		event.location = location
		event.begin = start
		event.end = end
		event.categories = ['lesson']
		event.uid = uid
		event.created = datetime.datetime.now()
		return event

	def add_event(self, name, location, start, end, uid):
		event = self.new_event(name, location, start, end, uid)
		self.events.append(event)
		
	def replace_multiple_periods(self):
		five_minutes = datetime.timedelta(minutes=5)
		
		events_to_remove = []
		double_periods = []
		for i in range(len(self.events)):
			if i > 0:
				start1 = self.events[i - 1].begin
				end1 = self.events[i - 1].end
				name1 = self.events[i - 1].name
				
				start2 = self.events[i].begin
				end2 = self.events[i].end
				name2 = self.events[i].name
				
				location = self.events[i].location
				uid = self.events[i-1].uid
				
				if (name1 == name2 and start2 - end1 == five_minutes) or (name1 == name2 and start2 < end1 and start1 < end2):
					events_to_remove += [self.events[i], self.events[i - 1]]
					double_period = self.new_event(name1, location, start1, end2, uid=uid)
					double_periods.append(double_period)
					
		for event in events_to_remove:
			if event in self.events:
				self.events.remove(event)
			
		self.events += double_periods
		
	def write_file(self, filename):
		self.events.sort(key = lambda event: event.name)
		self.events.sort(key = lambda event: event.begin)
		
		self.replace_multiple_periods()
		self.replace_multiple_periods()
			
		for event in self.events:
			self.calendar.events.add(event)
		
		dirname = os.path.dirname(os.path.abspath(__file__))
		filepath = os.path.join(dirname, 'Timetables', filename + '.ics')

		with open(filepath, 'w') as file:
			file.writelines(self.calendar.serialize_iter())
	
class TermDatesManager:
	def __init__(self):
		with open('term_dates.json', 'r') as file:
			term_data = json.loads(file.read())
		winter_timetable_start = datetime.date.fromisoformat(term_data['winter_timetable_start'])
		winter_timetable_end = datetime.date.fromisoformat(term_data['winter_timetable_end'])
		
		terms = [date_range(term) for term in term_data['terms']]
		dates_in_term = merge(terms)

		holidays = [date_range(holiday) for holiday in term_data['holidays']]
		dates_in_holidays = merge(holidays)

		remitted_periods_indexed_by_date = index(term_data['remitted_periods'], by=(lambda remitted_period: datetime.date.fromisoformat(remitted_period['date'])), unique=True)
		early_starts = [datetime.date.fromisoformat(remitted_lesson['date']) for remitted_lesson in term_data['remitted_periods'] if remitted_lesson['is_early_start']]
		lesson_rotations_indexed_by_date = index(term_data['lesson_rotations'], by=(lambda lesson: datetime.date.fromisoformat(lesson['date'])), unique=True)
		tutor_periods_indexed_by_date = index(term_data['tutor_periods'], by=(lambda tutor_period: datetime.date.fromisoformat(tutor_period['date'])), unique=True)
		late_starts_indexed_by_date = index(term_data['late_starts'], by=(lambda late_start: datetime.date.fromisoformat(late_start['date'])), unique=True)
		
		exams = {}
		for trial in term_data['exams']:
			for date in date_range(trial):
				exams[date] = trial['years']

		self.term_dates = []
		date = terms[0][0]
		end = terms[-1][-1]
		one_day = datetime.timedelta(days=1)
		week = 'A'
		week_number = 0
		while date != end:
			if date in dates_in_term and date not in dates_in_holidays:
				week_number = date.isocalendar()[1]
				if len(self.term_dates) > 0:
					if week_number != self.term_dates[-1]['week_number']:
						week = 'B' if week == 'A' else 'A'
				
				is_winter_timetable = (winter_timetable_start <= date <= winter_timetable_end and date.weekday() in [0, 2])
				years_off_lessons = exams[date] if date in exams else []
				lesson_rotations = lesson_rotations_indexed_by_date[date]['rotations'] if date in lesson_rotations_indexed_by_date else None
				remitted_periods = remitted_periods_indexed_by_date[date] if date in remitted_periods_indexed_by_date else []
				tutor_periods = tutor_periods_indexed_by_date[date]['periods'] if date in tutor_periods_indexed_by_date else []
				late_start_delay = late_starts_indexed_by_date[date]['delay'] if date in late_starts_indexed_by_date else 0
				
				term_date = {
						'date': date,
						'day_index': date.weekday(),
						'week_number': date.isocalendar()[1],
						'week': week,
						'remitted_periods': remitted_periods,
						'is_winter_timetable': is_winter_timetable,
						'years_off_lessons': years_off_lessons,
						'is_early_start': date in early_starts,
						'late_start_delay': late_start_delay,
						'lesson_rotations': lesson_rotations,
						'tutor_periods': tutor_periods
				}
				
				self.term_dates.append(term_date)
			
			date += one_day

class ISAMSDataManager:
	def __init__(self, username, password):
		self.username = username
		self.password = password
		self.periods = []
		self.lessons = []
	
	def request_xml_data(self):
		session = requests.Session()
		session.auth = HttpNtlmAuth(self.username, self.password)
		url = 'https://isams.harrowschool.org.uk/ReportServer?/iSAMS Built-in Reports/Timetable Manager/Timetable Export&rs:Format=XML'
		response = session.get(url)
		self.xml = ET.fromstring(response.text)
		
	def get_table_from_xml(self, index=0):
		table = self.xml[index][0]
		
		rows = []
		for node in table:
			rows.append(node.attrib)
		
		return rows
	
	def period_data_to_times(self, period_data):
		start_hour, start_minute = [int(number) for number in period_data['StartTime'].split(':')]
		start_time = datetime.time(start_hour, start_minute)
	
		end_hour, end_minute = [int(number) for number in period_data['EndTime'].split(':')]
		end_time = datetime.time(end_hour, end_minute)
	
		return (start_time, end_time)
	
	def process_periods_data(self):
		periods_data = self.get_table_from_xml(2)
		days_data = self.get_table_from_xml(1)
		days_data_indexed_by_code = index(days_data, by='Code1', unique=True)
		self.periods = []
		for period_data in periods_data:
			period_id = period_data['PeriodID']
			name = period_data['ShortName']
			day = days_data_indexed_by_code[period_data['DayCode']]['Name2']
			day_index = int(period_data['DayCode'][-1]) - 1
			week = 'B' if len(period_data['DayCode']) == 2 else 'A'
			start, end = self.period_data_to_times(period_data)
			winter_start = None
			winter_end = None
			
			today = datetime.datetime.now().date()
			difference = datetime.timedelta(hours=1, minutes=50)
			
			if day in ['Monday', 'Wednesday'] and name in ['3', '4', '5'] and start > datetime.time(hour=16):
				winter_start = start
				winter_end = end
				winter_start_datetime = datetime.datetime.combine(today, winter_start)
				winter_end_datetime = datetime.datetime.combine(today, winter_end)
				start = (winter_start_datetime - difference).time()
				end = (winter_end_datetime - difference).time()
			
			elif day in ['Monday', 'Wednesday'] and name in ['3', '4', '5'] and start < datetime.time(hour=16):
				summer_start_datetime = datetime.datetime.combine(today, start)
				summer_end_datetime = datetime.datetime.combine(today, end)
				winter_start = (summer_start_datetime + difference).time()
				winter_end = (summer_end_datetime + difference).time()
				
			period = {
				'period_id': period_id,
				'name': name,
				'day': day,
				'day_index': day_index,
				'week': week,
				'start': start,
				'end': end
			}
			
			if winter_start and winter_end:
				period['winter_start'] = winter_start
				period['winter_end'] = winter_end
			
			self.periods.append(period)
	
	def process_lessons_data(self):
		lessons_data = self.get_table_from_xml(3)
		
		for lesson_data in lessons_data:
			period_id = lesson_data['PeriodID1']
			division = lesson_data['SetCode']
			beak = lesson_data['Teacher']
			room = lesson_data['Room'] if 'Room' in lesson_data else ''
			year = int(lesson_data['Year'])
			
			lesson = {
				'period_id': period_id,
				'division': division,
				'beak': beak,
				'room': room,
				'year': year,
			}
		
			self.lessons.append(lesson)
			
	def link_lesson_to_period(self, lesson, period):
			del lesson['period_id']
			lesson['day'] = period['day']
			lesson['day_index'] = period['day_index']
			lesson['week'] = period['week']
			lesson['day'] = period['day']
			lesson['period_name'] = period['name']
			lesson['start'] = period['start']
			lesson['end'] = period['end']
			
			if 'winter_start' in period:
				lesson['winter_start'] = period['winter_start']
				lesson['winter_end'] = period['winter_end']
		
	def link_lessons_to_periods(self):
		periods_indexed_by_id = index(self.periods, by='period_id', unique=True)
		
		for lesson in self.lessons:
			period = periods_indexed_by_id[lesson['period_id']]
			self.link_lesson_to_period(lesson, period)
	
	def load(self):
		self.request_xml_data()
		self.process_periods_data()
		self.process_lessons_data()
		self.link_lessons_to_periods()

username = input("Username: ")
password = getpass("Password: ")

data_manager = ISAMSDataManager(username, password)
data_manager.load()
term_dates_manager = TermDatesManager()
periods_indexed_by_day_and_name = index(data_manager.periods, by=(lambda period: period['day'] + ' ' + period['name']), unique=True)
calendars_indexed_by_beak = {}
tzinfo = pytz.timezone('Europe/London')

for lesson in data_manager.lessons:
	
	for term_date in term_dates_manager.term_dates:
		
		if term_date['is_winter_timetable'] and 'winter_start' in lesson:
			start = lesson['winter_start']
			end = lesson['winter_end']
		else:
			start = lesson['start']
			end = lesson['end']
			
		start_datetime = datetime.datetime.combine(term_date['date'], start, tzinfo=tzinfo)
		end_datetime = datetime.datetime.combine(term_date['date'], end, tzinfo=tzinfo)
		
		if term_date['is_early_start']:
			start_datetime -= datetime.timedelta(minutes=20)
			end_datetime -= datetime.timedelta(minutes=20)
			
		late_start_delay = term_date['late_start_delay']
		if late_start_delay > 0 and lesson['period_name'] == '2a':
			start_datetime += datetime.timedelta(minutes=late_start_delay)
		
		if term_date['day_index'] == lesson['day_index'] and term_date['week'] == lesson['week'] and lesson['period_name'] not in term_date['remitted_periods'] and not term_date['lesson_rotations'] and lesson['year'] not in term_date['years_off_lessons'] and lesson['period_name'] not in term_date['tutor_periods']:
				beak = lesson['beak']
				room = lesson['room'] if 'room' in lesson else ''
				if beak not in calendars_indexed_by_beak:
					calendars_indexed_by_beak[beak] = TimetableManager()
				
				calendars_indexed_by_beak[beak].add_event(
					name = lesson['division'],
					location = room,
					start = start_datetime,
					end = end_datetime,
					uid = f"{beak}-{str(term_date['date'])}-{lesson['period_name']}-{lesson['division']}"
				)
		
		if term_date['lesson_rotations'] and term_date['week'] == lesson['week']:
			rotations = term_date['lesson_rotations']
			reversed_rotations = {value: key for (key, value) in rotations.items()}
			
			lesson_full_name = lesson['day'] + ' ' + lesson['period_name']
			if lesson_full_name in rotations.values():
				new_period_full_name = reversed_rotations[lesson_full_name]
				new_period = periods_indexed_by_day_and_name[new_period_full_name]
				
				start_datetime = datetime.datetime.combine(term_date['date'], new_period['start'], tzinfo=tzinfo)
				end_datetime = datetime.datetime.combine(term_date['date'], new_period['end'], tzinfo=tzinfo)
				
				if term_date['is_early_start']:
					start_datetime -= datetime.timedelta(minutes=20)
					end_datetime -= datetime.timedelta(minutes=20)
				
				calendars_indexed_by_beak[beak].add_event(
					name = lesson['division'],
					location = room,
					start = start_datetime,
					end = end_datetime,
					uid = f"{beak}-{str(term_date['date'])}-{lesson['period_name']}-{lesson['division']}"
				)

periods_indexed_by_day_index_and_name = index(data_manager.periods, by=(lambda period: str(period['day_index']) + ' ' + period['name']), unique=True)
for term_date in term_dates_manager.term_dates:
	tutor_period_index = 0
	for tutor_period in term_date['tutor_periods']:
		period = periods_indexed_by_day_index_and_name[str(term_date['day_index']) + ' ' + tutor_period]
		
		if term_date['is_winter_timetable'] and 'winter_start' in period:
			start = period['winter_start']
			end = period['winter_end']
		else:
			start = period['start']
			end = period['end']
			
		start_datetime = datetime.datetime.combine(term_date['date'], start, tzinfo=tzinfo)
		end_datetime = datetime.datetime.combine(term_date['date'], end, tzinfo=tzinfo)
		
		if term_date['is_early_start']:
			start_datetime -= datetime.timedelta(minutes=20)
			end_datetime -= datetime.timedelta(minutes=20)
		
		for beak in calendars_indexed_by_beak:
			calendars_indexed_by_beak[beak].add_event(
					name = 'Tutor Period',
					location = '',
					start = start_datetime,
					end = end_datetime,
					uid = f"{beak}-{str(term_date['date'])}-{period['name']}-TutorPeriod"		
				)

maxval = len(calendars_indexed_by_beak.keys())
bar = progressbar.ProgressBar(maxval= maxval, widgets=[progressbar.Bar('=', '[', ']'), ' ', progressbar.Percentage()])
bar.start()

i = 0
for beak in calendars_indexed_by_beak:
	calendars_indexed_by_beak[beak].write_file(beak)
	i += 1
	bar.update(i)
bar.finish()
