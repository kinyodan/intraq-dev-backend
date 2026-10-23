curl -X POST "https://intraq-backend.onrender.com \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=kinyodaniel@gmail.com" \
     -d "password=@Confucius@me2"
*

curl -X POST "https://intraq-backend.onrender.com/login" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=kinyodaniel@gmail.com" \
     -d "password=@Confucius@me2"


curl -X POST "https://intraq-backend.onrender.com/admin/create_inbox/CLE4EMWUFS" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2F1dGgubnguY29tIiwic3ViIjoidXNlci0xIiwiaWF0IjoxNzkyNjA0MTczLCJleHAiOjE3OTMyMDg5NzMsInNjb3BlIjoib3BlbmlkIn0.K1dRXi7SFrHwnY1EPY2qtoMIhVnrUJpwcs5LxqPkQIM" \
     -d '{
       "emails": [
       "info@intraq.pro", 
       "admin@intraq.pro", 
       "support@intraq.pro",
       "danielkinyo@intraq.pro",
       "integrations@intraq.pro",
       "operations@intraq.pro",
       ]
     }'


curl -X POST "https://intraq-backend.onrender.com/admin/create_inbox/CLE4EMWUFS" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2F1dGgubnguY29tIiwic3ViIjoidXNlci0xIiwiaWF0IjoxNzkyNjUyNzQ0LCJleHAiOjE3OTMyNTc1NDQsInNjb3BlIjoib3BlbmlkIn0.sXLNnoBf72zdFbmjEs-iy6Bynh8ayyzQmXR7KuXyCns" \
     -d '{
       "emails": [
       "info@intraq.pro", 
       "admin@intraq.pro", 
       "support@intraq.pro",
       "danielkinyo@intraq.pro",
       "integrations@intraq.pro",
       "operations@intraq.pro"
       ]
     }'



curl -X POST "http://127.0.0.1:8000/admin/create_inbox/CLE4EMWUFS" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2F1dGgubnguY29tIiwic3ViIjoidXNlci0xIiwiaWF0IjoxNzkyNjUyNzQ0LCJleHAiOjE3OTMyNTc1NDQsInNjb3BlIjoib3BlbmlkIn0.sXLNnoBf72zdFbmjEs-iy6Bynh8ayyzQmXR7KuXyCns" \
     -d '{
       "emails": [
       "info@intraq.pro", 
       "admin@intraq.pro", 
       "support@intraq.pro",
       "danielkinyo@intraq.pro",
       "integrations@intraq.pro",
       "operations@intraq.pro"
       ]
     }'


eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2F1dGgubnguY29tIiwic3ViIjoidXNlci0xIiwiaWF0IjoxNzkyNjA0MTczLCJleHAiOjE3OTMyMDg5NzMsInNjb3BlIjoib3BlbmlkIn0.K1dRXi7SFrHwnY1EPY2qtoMIhVnrUJpwcs5LxqPkQIM