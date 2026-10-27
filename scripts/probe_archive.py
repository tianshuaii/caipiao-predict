from lottery.collectors import client, ZHCW_URL
with client() as http:
    for end in ['2012154', '2013001']:
        for referer in ['https://www.cwl.gov.cn/', 'https://www.zhcw.com/']:
            r=http.get(ZHCW_URL,params=dict(transactionType='10001001',lotteryId=1,issueCount=0,startIssue='2003001',endIssue=end,type=1,pageNum=1,pageSize=100),headers={'Referer':referer})
            print(end, referer, r.status_code, len(r.content), r.text[:90],flush=True)
