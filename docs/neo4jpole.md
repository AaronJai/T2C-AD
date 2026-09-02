## Exploration queries on NEO4J POLE

### label
Person
Location
Phone
Email
Officer
PostCode
Area
PhoneCall
Crime
Object
Vehicle

### relationshipType
CURRENT_ADDRESS
HAS_PHONE
HAS_EMAIL
HAS_POSTCODE
POSTCODE_IN_AREA
LOCATION_IN_AREA
KNOWS_SN
KNOWS
CALLER
CALLED
KNOWS_PHONE
OCCURRED_AT
INVESTIGATED_BY
INVOLVED_IN
PARTY_TO
FAMILY_REL
KNOWS_LW

### propertyKey
nhs_no
name
surname
address
postcode
longitude
latitude
phoneNo
email_address
badge_no
rank
code
areaCode
call_date
call_type
call_duration
call_time
id
date
type
last_outcome
make
model
year
reg
rel_type
partition
charge
description
community
age
note
data
nodes
relationships
style
visualisation


### per-label counts and sample

#### Person (n=369)
limit=5
"(:Person {nhs_no: 117-66-8129, surname: Hamilton, name: Todd})"
"(:Person {nhs_no: 991-70-5333, surname: Hamilton, name: Benjamin})"
"(:Person {nhs_no: 620-83-1546, surname: Campbell, name: Nancy})"
"(:Person {nhs_no: 595-90-8809, surname: Garcia, name: Todd})"
"(:Person {nhs_no: 556-65-1110, surname: Turner, name: Rachel})"

#### Location (n=14904)
limit=5
"(:Location {address: 178 Polding Street, latitude: 53.530988, postcode: WN3 4NL, longitude: -2.61741})"
"(:Location {address: 6 Gypsy Lane, latitude: 53.59882, postcode: OL11 3HA, longitude: -2.177916})"
"(:Location {address: 116 Myrtle Street, latitude: 53.582711, postcode: BL1 3AH, longitude: -2.442103})"
"(:Location {address: 53 Birch Lane, latitude: 53.471473, postcode: SK16 5AP, longitude: -2.077441})"
"(:Location {address: 27 Maiden Close, latitude: 53.50318, postcode: OL7 9PL, longitude: -2.105902})"

#### Phone (n=328)
limit=5
(:Phone {phoneNo: 0-(070)893-3322})
(:Phone {phoneNo: 5-(997)640-5104})
(:Phone {phoneNo: 9-(882)417-7531})
(:Phone {phoneNo: 3-(989)030-3439})
(:Phone {phoneNo: 9-(184)752-7135})

#### Email (n=328)
limit=5
(:Email {email_address: bhamilton3h@twitter.com})
(:Email {email_address: ncampbell1@marriott.com})
(:Email {email_address: tgarcia3@macromedia.com})
(:Email {email_address: rturner4@wsj.com})
(:Email {email_address: mkelly5@symantec.com})

#### Officer (n=1000)
limit=5
"(:Officer {badge_no: 80-1015383, surname: Lineen, name: Sophronia, rank: Sergeant})"
"(:Officer {badge_no: 70-0643982, surname: Glossup, name: Uri, rank: Inspector})"
"(:Officer {badge_no: 57-6110377, surname: Hannam, name: Christian, rank: Police Constable})"
"(:Officer {badge_no: 18-0221971, surname: Lampet, name: Eimile, rank: Chief Inspector})"
"(:Officer {badge_no: 38-1719233, surname: Makinson, name: Wynn, rank: Chief Inspector})"

#### PostCode (n=14196)
limit=5
(:PostCode {code: WN3 4NL})
(:PostCode {code: OL11 3HA})
(:PostCode {code: BL1 3AH})
(:PostCode {code: SK16 5AP})
(:PostCode {code: OL7 9PL})

#### Area (n=93)
limit=5
(:Area {areaCode: WN3})
(:Area {areaCode: OL1})
(:Area {areaCode: BL1})
(:Area {areaCode: SK1})
(:Area {areaCode: OL7})

#### PhoneCall (n=534)
limit=5
"(:PhoneCall {call_date: 04/08/2017, call_time: 00:32, call_type: CALL, call_duration: 38})"
"(:PhoneCall {call_date: 27/08/2017, call_time: 14:44, call_type: CALL, call_duration: 1})"
"(:PhoneCall {call_date: 14/08/2017, call_time: 23:49, call_type: SMS, call_duration: 39})"
"(:PhoneCall {call_date: 15/08/2017, call_time: 07:12, call_type: SMS, call_duration: 3})"
"(:PhoneCall {call_date: 19/08/2017, call_time: 09:55, call_type: CALL, call_duration: 13})"

#### Crime (n=28762)
limit=5
"(:Crime {date: 24/08/2017, id: 10305fdb9613b698a9fe8a26468564ebe15ba01eb870994739180ffc51440c31, type: Public order, last_outcome: Investigation complete; no suspect identified})"
"(:Crime {date: 15/08/2017, id: 8dae6537bfb64a92cc91539ce9e76abf729f60592a9c503300905130afaacef4, type: Public order, last_outcome: Investigation complete; no suspect identified})"
"(:Crime {date: 31/08/2017, id: 9bc0db533b9248a8b3a7ac151f273fe01f25ad72b394dd5cc6ef9bd6558eb707, type: Public order, last_outcome: Investigation complete; no suspect identified})"
"(:Crime {date: 7/08/2017, id: df4e954114d147be364d17d580cda1214ff694b614bdf76baa0a640d5bda74d3, type: Public order, last_outcome: Investigation complete; no suspect identified})"
"(:Crime {date: 19/08/2017, id: 34f309ebafbd1c46b5c4832f63321a10330835a5ae323952419439b69633bb2c, last_outcome: Unable to prosecute suspect, type: Public order})"

#### Object (n=7)
limit=10
"(:Object {description: 43 Cannabis Plants, 3kg Prepared Cannabis, id: 2346erfsdff223, type: Evidence})"
"(:Object {description: £3,500 currency, id: 484brolsdfb666, type: Evidence})"
"(:Object {description: 120g Packaged Cannabis, type: Evidence})"
"(:Object {description: £550 currency, type: Evidence})"
"(:Object {description: £830 currency, type: Evidence})"
"(:Object {description: 250g Loose Cannabis, type: Evidence})"
"(:Object {description: Electronic Scale, type: Evidence})"

#### Vehicle (n=1000)
limit=5
"(:Vehicle {reg: RY52 APF, year: 2005, model: 4Runner, make: Toyota})"
"(:Vehicle {reg: RH42 TAB, year: 1992, model: XJ Series, make: Jaguar})"
"(:Vehicle {reg: LW72 POF, year: 1985, model: Coupe GT, make: Audi})"
"(:Vehicle {reg: TZ72 UGE, year: 2011, model: xB, make: Scion})"
"(:Vehicle {reg: BN52 ACF, year: 2012, model: Sierra 2500, make: GMC})"


### Relationships w/ date-like properties
```
MATCH ()-[r]->()
RETURN type(r) AS rel_type, keys(r) AS rel_props, count(*) AS total
ORDER BY rel_type
```

rel_type,rel_props,total
CALLED,[],534
CALLER,[],534
CURRENT_ADDRESS,[],368
FAMILY_REL,[rel_type],155
HAS_EMAIL,[],328
HAS_PHONE,[],328
HAS_POSTCODE,[],14904
INVESTIGATED_BY,[],28762
INVOLVED_IN,[],985
KNOWS,[],586
KNOWS_LW,[],80
KNOWS_PHONE,[],118
KNOWS_SN,[],241
LOCATION_IN_AREA,[],14904
OCCURRED_AT,[],28762
PARTY_TO,[],55
POSTCODE_IN_AREA,[],14196


#### Entity ambiguity
```
MATCH (p:Person)
RETURN p.surname AS surname, count(*) AS n
ORDER BY n DESC LIMIT 20
```
surname,n
Fuller,5
Murray,5
Nguyen,5
Austin,5
Knight,4
Jackson,4
Robertson,4
Foster,4
Martin,4
Rogers,4
Williamson,4
Hughes,4
Butler,4
Moreno,4
Hanson,4
Bradley,4
Ford,4
Mason,4
Gibson,3
Rodriguez,3

```
MATCH (p:Person)
RETURN p.name AS first, p.surname AS surname, count(*) AS n
ORDER BY n DESC LIMIT 20
```
first,surname,n
Andrea,George,2
Anne,Rice,2
Nancy,Campbell,1
Rachel,Turner,1
Mildred,Kelly,1
Stephen,Perez,1
Antonio,Washington,1
Gregory,Rodriguez,1
Nicholas,Mason,1
Lawrence,Warren,1
Phillip,Myers,1
Mary,Young,1
Stephanie,Hughes,1
Pamela,Gibson,1
Paul,Nguyen,1
Denise,Rodriguez,1
Louis,Parker,1
Sharon,White,1
Philip,Mason,1
Todd,Garcia,1

### Schema ambiguity
```
MATCH (p:Person)-[r]-(:Person)
RETURN type(r), count(*) ORDER BY count(*) DESC
```
type(r),count(*)
KNOWS,1172
KNOWS_SN,482
FAMILY_REL,310
KNOWS_PHONE,236
KNOWS_LW,160


**Schema ambiguity reframed**
```
MATCH (a)-[:PARTY_TO]->(b) RETURN labels(a), labels(b), count(*)
```
labels(a),labels(b),count(*)
[Person],[Crime],55

```
MATCH (a)-[:INVOLVED_IN]->(b) RETURN labels(a), labels(b), count(*)
```
labels(a),labels(b),count(*)
[Vehicle],[Crime],978
[Object],[Crime],7


```
MATCH (p1:Person)-[r]-(p2:Person)
WITH p1, p2, collect(DISTINCT type(r)) AS rel_types
WHERE size(rel_types) > 1
RETURN p1.name, p1.surname, p2.name, p2.surname, rel_types
LIMIT 20
```

p1.name,p1.surname,p2.name,p2.surname,rel_types
Todd,Hamilton,Benjamin,Hamilton,"[FAMILY_REL, KNOWS]"
Benjamin,Hamilton,Todd,Hamilton,"[FAMILY_REL, KNOWS]"
Benjamin,Hamilton,Frances,Sullivan,"[KNOWS, KNOWS_PHONE]"
Benjamin,Hamilton,Amanda,Alexander,"[KNOWS_SN, KNOWS]"
Benjamin,Hamilton,Brandon,Martin,"[KNOWS_SN, KNOWS]"
Benjamin,Hamilton,Joshua,Fields,"[KNOWS, KNOWS_SN]"
Benjamin,Hamilton,Frank,Taylor,"[KNOWS_SN, KNOWS]"
Benjamin,Hamilton,Diane,Cox,"[KNOWS, KNOWS_SN]"
Benjamin,Hamilton,Matthew,Howell,"[KNOWS_SN, KNOWS]"
Benjamin,Hamilton,Kathryn,Allen,"[KNOWS_SN, KNOWS]"
Benjamin,Hamilton,Phyllis,Murray,"[KNOWS, KNOWS_SN]"
Nancy,Campbell,Carl,Hayes,"[KNOWS, KNOWS_PHONE]"
Nancy,Campbell,Angela,Mccoy,"[KNOWS, KNOWS_SN]"
Todd,Garcia,Rachel,Turner,"[KNOWS, KNOWS_LW]"
Todd,Garcia,Phillip,Perry,"[KNOWS, KNOWS_PHONE]"
Todd,Garcia,Angela,Mccoy,"[KNOWS_SN, KNOWS]"
Rachel,Turner,Todd,Garcia,"[KNOWS, KNOWS_LW]"
Rachel,Turner,Eric,Gutierrez,"[KNOWS, KNOWS_PHONE]"
Mildred,Kelly,Stephen,Perez,"[KNOWS_LW, KNOWS]"
Mildred,Kelly,Jeffrey,Campbell,"[KNOWS_PHONE, KNOWS]"

**vechiles**
```
MATCH (v:Vehicle)-[r]-() RETURN type(r), count(*)
```
type(r),count(*)
INVOLVED_IN,978








MATCH (c:Crime) RETURN c.type AS crime_type, count(*) AS n ORDER BY n DESC LIMIT 10
crime_type,n
Violence and sexual offences,8765
Public order,4839
Criminal damage and arson,3587
Burglary,2807
Vehicle crime,2598
Other theft,2140
Shoplifting,1427
Other crime,651
Robbery,541
Theft from the person,423

MATCH (:Crime)-[:INVESTIGATED_BY]->(o:Officer) RETURN o.surname, o.name, count(*) AS n ORDER BY n DESC LIMIT 10
o.surname,o.name,n
DeSousa,Madelon,50
Ings,Cloe,47
Notti,Kania,46
Nettles,Worthy,45
Miskimmon,Ricca,44
Klehyn,Olenolin,44
Skynner,Winonah,44
Greensall,Simmonds,43
Orcott,Hollyanne,43
Vinson,Hedy,43

MATCH (:Crime)-[:OCCURRED_AT]->(:Location)-[:LOCATION_IN_AREA]->(a:Area) RETURN a.areaCode, count(*) AS n ORDER BY n DESC LIMIT 10
a.areaCode,n
M1,975
BL1,860
BL3,814
M40,766
M9,699
BL9,623
M14,562
BL4,562
BL2,562
M6,540


MATCH (p:Person {surname: 'Ford'})
OPTIONAL MATCH (p)-[:PARTY_TO]->(c:Crime)
OPTIONAL MATCH (p)-[:CURRENT_ADDRESS]->(l:Location)
RETURN p.name, p.nhs_no, count(DISTINCT c) AS crimes, collect(DISTINCT l.address) AS addresses

p.name,p.nhs_no,crimes,addresses
Philip,600-92-0796,0,[12 Banner Street]
Dennis,692-38-3827,0,[66 Falcon Street]
Jimmy,483-40-6408,0,[195 Whitchurch Road]
Deborah,838-45-9343,0,[42 Haddon Street]



MATCH (c:Crime) RETURN c.date, count(*) AS n ORDER BY c.date
c.date,n
1/08/2017,923
10/08/2017,972
11/08/2017,930
12/08/2017,900
13/08/2017,904
14/08/2017,959
15/08/2017,922
16/08/2017,918
17/08/2017,951
18/08/2017,965
19/08/2017,928
2/08/2017,932
20/08/2017,924
21/08/2017,899
22/08/2017,934
23/08/2017,894
24/08/2017,957
25/08/2017,927
26/08/2017,903
27/08/2017,927
28/08/2017,1014
29/08/2017,958
3/08/2017,920
30/08/2017,871
31/08/2017,933
4/08/2017,976
5/08/2017,913
6/08/2017,897
7/08/2017,897
8/08/2017,886
9/08/2017,928

MATCH (c:Crime)-[:OCCURRED_AT]->(l:Location)-[:LOCATION_IN_AREA]->(a:Area {areaCode:'M1'})
RETURN c.date, count(*) AS n ORDER BY c.date
c.date,n
1/08/2017,35
10/08/2017,40
11/08/2017,47
12/08/2017,29
13/08/2017,24
14/08/2017,24
15/08/2017,27
16/08/2017,30
17/08/2017,21
18/08/2017,36
19/08/2017,31
2/08/2017,28
20/08/2017,39
21/08/2017,33
22/08/2017,30
23/08/2017,34
24/08/2017,37
25/08/2017,28
26/08/2017,46
27/08/2017,30
28/08/2017,36
29/08/2017,20
3/08/2017,28
30/08/2017,29
31/08/2017,42
4/08/2017,41
5/08/2017,31
6/08/2017,30
7/08/2017,21
8/08/2017,22
9/08/2017,26


MATCH (pc:PhoneCall)-[:CALLED]->(p:Phone) RETURN p.phoneNo, count(*) AS n ORDER BY n DESC LIMIT 5
p.phoneNo,n
0-(008)297-1581,8
0-(649)542-7430,6
0-(070)893-3322,6
0-(608)989-7174,6
0-(403)215-3959,6

MATCH (p:Phone {phoneNo: "0-(008)297-1581"})<-[:CALLER]-(pc:PhoneCall)-[:CALLED]->(p2:Phone)
RETURN p2.phoneNo, pc.call_date, pc.call_time, pc.call_type
ORDER BY pc.call_date, pc.call_time;
p2.phoneNo,pc.call_date,pc.call_time,pc.call_type
9-(984)524-5395,04/08/2017,00:32,CALL
9-(984)524-5395,20/08/2017,00:05,CALL