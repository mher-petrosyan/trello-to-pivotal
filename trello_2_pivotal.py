import datetime
import json

import requests
from trello import TrelloClient

from varys.logger import logger


class TrelloToPivotal:

    def __init__(self, project_id, board_id, api_key, trello_token, pivotal_token, redis_client):
        self.trello_board = board_id
        self.pivotal_project = project_id
        self.trello_key = api_key
        self.trello_token = trello_token
        self.pivotal_token = pivotal_token
        self.trello_client = TrelloClient(
            api_key=self.trello_key,
            token=self.trello_token,
        )
        self.redis_client = redis_client

    def call_trello_api(self):
        """
        This function call trello api and return list of dictionaries, where each dictionary
        is story from board
        :return:
        """
        params = {'key': self.trello_key, 'token': self.trello_token}
        response = requests.get('https://api.trello.com/1/boards/{}/cards'.format(self.trello_board), params=params)
        return response.json()

    def create_card(self, list_name, card_title):
        payload = {'name': card_title, 'current_state': list_name}
        headers = {'X-TrackerToken': self.pivotal_token, 'Content-type': 'application/json',
                   'Accept': 'application/json'}
        response = requests.post(
            'https://www.pivotaltracker.com/services/v5/projects/{}/stories'.format(self.pivotal_project),
            data=json.dumps(payload), headers=headers).json()
        return response['id']

    def delete_card(self, pivotal_story_id):
        headers = {'X-TrackerToken': self.pivotal_token, 'Content-type': 'application/json',
                   'Accept': 'application/json'}
        response = requests.delete('https://www.pivotaltracker.com/services/v5/projects/{}/stories/{}'
                                   ''.format(self.pivotal_project, int(pivotal_story_id)), headers=headers)
        logger.info('Pivotal story with {} id is deleted\n{}'.format(pivotal_story_id, response))

    def update_card(self, pivotal_story_id, action):
        data = action['data']
        old = data['old']
        card = data['card']
        old_field = list(old.items())[0][0]
        payload = {}
        if old_field == 'name':  # card-name.json
            new_name = card['name']
            payload = {'name': new_name}
        if old_field == 'idList':  # card-list.json
            new_state = data['listAfter']['name']
            payload = {'current_state': new_state}
            if new_state == 'started' or new_state == 'finished' or new_state == 'delivered':
                due_date = self.trello_client.get_card(card_id=card['id']).due_date
                now = datetime.datetime.now()
                if due_date.day - now.day == 0:
                    payload.update({"estimate": 0})
                if due_date.day - now.day == 1:
                    payload.update({"estimate": 0})
                if due_date.day - now.day == 2:
                    payload.update({"estimate": 1})
                if due_date.day - now.day == 3:
                    payload.update({"estimate": 2})
                if due_date.day - now.day == 4:
                    payload.update({"estimate": 2})
                if due_date.day - now.day > 4:
                    payload.update({"estimate": 3})
        if old_field == 'desc':  # card-desc.json
            new_desc = card['desc']
            payload = {'description': new_desc}
        if old_field == 'due':  # card-due.json
            payload = {}
            trello = self.trello_client
            card_id = card['id']
            card_t = trello.get_card(card_id)
            due = card_t.due_date
            if not due:
                payload = {'estimate': 0}
            else:
                due_date = due.day
                now = datetime.datetime.now()
                if due_date - now.day == 0:
                    payload = {'estimate': 0}
                if due_date - now.day == 1:
                    payload = {'estimate': 0}
                if due_date - now.day == 2:
                    payload = {'estimate': 1}
                if due_date - now.day == 3:
                    payload = {"estimate": 2}
                if due_date - now.day == 4:
                    payload = {'estimate': 2}
                if due_date - now.day > 4:
                    payload = {'estimate': 3}
        if old_field == 'closed':  # card-archive.json
            self.delete_card(pivotal_story_id)
            return
        headers = {'X-TrackerToken': self.pivotal_token, 'Content-type': 'application/json',
                   'Accept': 'application/json'}
        response = requests.put('https://www.pivotaltracker.com/services/v5/projects/{}/stories/{}'
                                ''.format(self.pivotal_project, int(pivotal_story_id)), data=json.dumps(payload),
                                headers=headers).json()

        logger.info('Pivotal story with {} id is updated\n{}'.format(pivotal_story_id, response))

    def add_label_to_card(self, pivotal_story_id, card_id):
        labels = self.trello_client.get_card(card_id=card_id).labels
        label_names = [i.name for i in labels]
        payload = {'labels': label_names}
        headers = {'X-TrackerToken': self.pivotal_token, 'Content-type': 'application/json',
                   'Accept': 'application/json'}
        response = requests.put('https://www.pivotaltracker.com/services/v5/projects/{}/stories/{}'
                                ''.format(self.pivotal_project, int(pivotal_story_id)), data=json.dumps(payload),
                                headers=headers).json()
        logger.info('Pivotal story label with {} id is updated\n{}'.format(pivotal_story_id, response))

    def update_label(self, pivotal_story_id, action):
        data = action['data']
        old = data['old']
        card = data['card']
        old_field = list(old.items())[0][0]
        if old_field == 'name':  # card-name.json
            labels = self.trello_client.get_card(card_id=card['id']).labels
            label_names = [i.name for i in labels]
            payload = {'labels': label_names}
            headers = {'X-TrackerToken': self.pivotal_token, 'Content-type': 'application/json',
                       'Accept': 'application/json'}
            response = requests.put('https://www.pivotaltracker.com/services/v5/projects/{}/stories/{}'
                                    ''.format(self.pivotal_project, int(pivotal_story_id)), data=payload,
                                    headers=headers).json()
        logger.info('Pivotal story label with {} id is updated\n{}'.format(pivotal_story_id, response or 'color'))

    def initialize_board(self):
        trello_stories = self.call_trello_api()
        params = {'key': self.trello_key, 'token': self.trello_token}
        id_couples = []
        for card in trello_stories:
            if not self.redis_client.get(card['id'] + "_created"):
                name = card['name']
                description = card['desc']
                label = [i['name'] for i in card['labels']]
                status = requests.get('https://trello.com/1/lists/{}'.format(card['idList']), params=params)
                list_name = status.json()['name']
                due = card['due']
                payload = {'name': name, 'description': description, 'labels': label, 'current_state': list_name}
                if due:
                    due_date = datetime.datetime.strptime(due, "%Y-%m-%dT%H:%M:%S.%fZ").day
                    now = datetime.datetime.now()
                    if due_date - now.day == 0:
                        payload.update({'estimate': 0})
                    if due_date - now.day == 1:
                        payload.update({'estimate': 0})
                    if due_date - now.day == 2:
                        payload.update({'estimate': 1})
                    if due_date - now.day == 3:
                        payload.update({'estimate': 2})
                    if due_date - now.day == 4:
                        payload.update({'estimate': 2})
                    if due_date - now.day > 4:
                        payload.update({'estimate': 3})
                headers = {'X-TrackerToken': self.pivotal_token, 'Content-type': 'application/json',
                           'Accept': 'application/json'}
                response = requests.post(
                    'https://www.pivotaltracker.com/services/v5/projects/{}/stories'.format(self.pivotal_project),
                    data=json.dumps(payload), headers=headers).json()
                id_couples.append((card['id'], response['id']))
                self.redis_client.set(card['id'] + "_created", card['name'])
            else:
                logger.warn(
                    f'Card with id: "{card["id"] + "_created"}" and name:'
                    f' "{self.redis_client.get(card["id"] + "_created")}" already exists')
        return id_couples


if __name__ == '__main__':
    from os import path
    from configparser import ConfigParser

    credentials = ConfigParser()
    credentials.read(path.join(path.dirname(__file__), 'credentials.ini'))
    board_id = credentials['trello']['board_id']
    api_key = credentials['trello']['api_key']
    token = credentials['trello']['token']
    pivotal_project_id = credentials['pivotal']['project_id']
    pivotal_token = credentials['pivotal']['token']
    a = TrelloToPivotal(project_id=pivotal_project_id,
                        board_id=board_id,
                        api_key=api_key,
                        trello_token=token,
                        pivotal_token=pivotal_token)