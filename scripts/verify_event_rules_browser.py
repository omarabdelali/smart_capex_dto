"""Live verification of sustained event displays and +1 CBR effects."""
from verify_network_events_browser import verify as verify_events
from verify_biz_population_cbr import verify as verify_cbr


if __name__ == '__main__':
    verify_events()
    verify_cbr()
