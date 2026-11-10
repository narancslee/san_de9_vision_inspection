# Simulated state derived from the latest valid inspection decision.
std_msgs/Header source_header
uint8 UNAVAILABLE=0
uint8 ACCEPT=1
uint8 REVIEW=2
uint8 REJECT=3
uint8 state
# waiting, fresh, invalid, or stale; not a physical actuator command.
string reason
