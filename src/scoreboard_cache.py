import time
import threading

from mongo_utils import get_db_manager, get_teams, get_services


class ConcurrentUpdateException(Exception):
    pass


class ScoreboardCache:
    def __init__(self, config: dict):
        db, mongo_client = get_db_manager(config['mongo'])
        self.mongoClient = mongo_client
        self.mongoConfig = config['mongo']
        self.updateLatency = config['misc']['scoreboard_cache_update_latency']
        self.atkWeight = config['misc']['atk_weight']
        self.defWeight = config['misc']['def_weight']
        self.slaWeight = config['misc']['sla_weight']
        self.baseScore = config['misc']['base_score']
        self.services = {s['service_id']: s for s in get_services(db)}
        self.lastUpdate = 0
        self.teams = self.getTeams()
        # this mutex is to make sure the teams update is not done concurrently
        self.mutex = threading.Lock()

    def getTeams(self):
        # this is a "private" method
        db, _ = get_db_manager(self.mongoConfig, self.mongoClient)
        exposed_fields = {"ip_addr", "name", "points", "last_pts_update"}
        # this method "sanitizes" teams, by removing attributes that must not be publicly exposed,
        # like stolen_flags, and at the same time it adds "overall_score" field and
        # service_status[service_name]['status'] for each service (for last status update)
        teams = sorted([t for t in get_teams(db)], key=lambda t: t['team_id'])
        for team in teams:
            # mapping: {service_name: service_points}
            points = {self.services[service_points['service_id']]['name']: service_points
                      for service_points in team['points']}
            for service_name in points.keys():
                points[service_name].pop('service_id')
            team['points'] = points
            team_checks = sorted([check for check in team['checks']],
                                 key=lambda c: c['timestamp'], reverse=True)
            remove_keys = []
            for k in team.keys():
                if k not in exposed_fields:
                    remove_keys.append(k)
            for k in remove_keys:
                team.pop(k)
            team['overall_score'] = self.baseScore
            # note: def pts are assumed to be negative, so no need for "-=" or negative weight
            for service_name in points.keys():
                team['overall_score'] += points[service_name]['atk_pts'] * self.atkWeight
                team['overall_score'] += points[service_name]['def_pts'] * self.defWeight
                team['overall_score'] += points[service_name]['sla_pts'] * self.slaWeight
            team['service_status'] = {}
            i = 0
            while len(team['service_status']) < len(self.services) and i < len(team_checks):
                check = team_checks[i]
                service_name = self.services[check['service_id']]['name']
                if service_name not in team['service_status']:
                    team['service_status'][service_name] = check['status']
                i += 1
        self.lastUpdate = int(time.time())
        return teams

    def getStats(self, wait=True):
        # optimistic check
        if int(time.time()) >= self.lastUpdate + self.updateLatency:
            acquired = self.mutex.acquire(blocking=False)
            if acquired:
                self.teams = self.getTeams()
                self.mutex.release()
            else:
                if wait:
                    # wait for the already running update to finish
                    while self.mutex.locked():
                        pass
                else:
                    # primarily used for testing
                    raise ConcurrentUpdateException
        return self.teams
