from db.schema import Observation as Row
def persist(session, observation_id):
    session.add(Row(observation_id=observation_id))
