# Original input image header.
std_msgs/Header header
# Explicit decision codes; zero is reserved for an unset/invalid decision.
uint8 ACCEPT=1
uint8 REVIEW=2
uint8 REJECT=3
uint8 decision
# Processed longer and shorter sides in millimeters.
float64 length_mm
float64 width_mm
