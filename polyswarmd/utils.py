def bool_list_to_int(bs):
    return sum([1 << n if b else 0 for n, b in enumerate(bs)])

def int_to_bool_list(i):
    s = format(i, 'b')
    return [x == '1' for x in s[::-1]]
