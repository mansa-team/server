import numpy, pandas

def normalize(data, order):
    columns = list(data.columns)
    orderedColumns = [col for col in order if col in columns]
    remainingColumns = [col for col in columns if col not in orderedColumns]
    remainingColumns.sort()
    newOrder = orderedColumns + remainingColumns

    return data[newOrder]