import pandas as pd

master_nic = pd.read_excel("Master NIC 11-09-25 UP.xlsx", sheet_name='Master SAP 11-09-25')

print(master_nic.head())

barcodes = [
    "810181530650",
    "810181531091",
    "858050008886",
    "6972984886595",
    "810181530698",
    "810181531053",
    "858050008695",
    "6955265614841",
    "6955265614858",
    "6955265614889",
    "6955265614896",
    "6972885467466",
    "6972885467473",
    "6972885467480",
    "6972885469385",
    "6936798318635",
    "6936798318642",
    "6936798318659",
    "6936798320706",
    "6936798320713",
    "6936798320751",
    "6936798320836",
    "810181530025",
    "810181530438",
    "810181530445",
    "858050008541",
    "810181530704",
    "810181530711",
    "810181530728"
]

item_numbers = []

for barcode in barcodes:
    row_str = master_nic[master_nic['Bar Code'].str.contains(barcode, na=False)]
    item_no = row_str['Item No.']
    # row_int = master_nic[master_nic['Bar Code'].eq( int(barcode) )]
    # item_no = row_int['Item No.']
    print('\nbar', barcode)
    if not item_no.empty:
        print('item code', item_no.iloc[0])
        item_numbers.append(item_no.iloc[0])
    else:
        print('item code NOT FOUND')
        item_numbers.append(None)
    
    
print(item_numbers)
print(len(item_numbers))
print(len(barcodes))