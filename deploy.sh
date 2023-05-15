
PROJECT=loplat-beagle
REGIST_REGION=asia.gcr.io
REGION=asia-northeast1
ENV_FILE=env.yaml
LOG_LEVEL=debug

SERVICE=cloud_logging_handler
VERSION=latest
IMAGE=$REGIST_REGION/$PROJECT/$SERVICE:$VERSION

echo $PROJECT $OPTION $SERVICE

echo "start building docker image"
docker build -f Dockerfile -t $IMAGE --build-arg LOG_LEVEL=$LOG_LEVEL .
echo "push image to container registry"
docker push $IMAGE
echo "deploy image to cloud run"
gcloud run deploy $SERVICE \
--project $PROJECT \
--image $IMAGE \
--region $REGION \
--env-vars-file $ENV_FILE