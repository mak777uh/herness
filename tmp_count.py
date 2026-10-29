import json 
d=json.load(open('portfolio.json',encoding='utf-8')) 
r=d['repos'] 
print('repos',len(r)) 
print('unique',len(set(x['name'] for x in r))) 
names=[x['name'] for x in r] 
print('\n'.join(names)) 
