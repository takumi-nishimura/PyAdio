import pstats
from pstats import SortKey

# Create a Stats object
p = pstats.Stats('profile_output.txt')

# Sort the statistics by cumulative time and print the top 20
print("Stats sorted by cumulative time (cumtime):")
p.sort_stats(SortKey.CUMULATIVE).print_stats(20)

# Sort the statistics by internal time and print the top 20
print("\nStats sorted by internal time (tottime):")
p.sort_stats(SortKey.TIME).print_stats(20)
