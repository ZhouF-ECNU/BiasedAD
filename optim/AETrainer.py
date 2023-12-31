from base.base_trainer import BaseTrainer
from base.base_dataset import BaseADDataset
from base.base_net import BaseNet
from sklearn.metrics import roc_auc_score, precision_recall_curve, auc, confusion_matrix

import logging
import time
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np


class AETrainer(BaseTrainer):

    def __init__(self, optimizer_name: str = 'adam', lr: float = 0.001, n_epochs: int = 150, lr_milestones: tuple = (),
                 batch_size: int = 128, weight_decay: float = 1e-6, device: str = 'cuda', n_jobs_dataloader: int = 0):
        super().__init__(optimizer_name, lr, n_epochs, lr_milestones, batch_size, weight_decay, device,
                         n_jobs_dataloader)

        # Results
        self.train_time = None
        self.test_auc = None
        self.test_time = None

    def train(self, dataset, ae_net: BaseNet):
        logger = logging.getLogger()

        # Get train data loader
        train_loader, _ = dataset.loaders(batch_size=self.batch_size, num_workers=self.n_jobs_dataloader)

        # Set loss
        criterion = nn.MSELoss(reduction='none')

        # Set device
        ae_net = ae_net.to(self.device)
        criterion = criterion.to(self.device)

        # Set optimizer (Adam optimizer for now)
        optimizer = optim.Adam(ae_net.parameters(), lr=self.lr, weight_decay=self.weight_decay)

        # Set learning rate scheduler
        scheduler = optim.lr_scheduler.MultiStepLR(optimizer, milestones=self.lr_milestones, gamma=0.1)

        # Training
        start_time = time.time()
        ae_net.train()
        for epoch in range(self.n_epochs):

            scheduler.step()

            epoch_loss = 0.0
            n_batches = 0
            epoch_start_time = time.time()
            for data in train_loader:
                # if model is BiasedAD
                if (len(data) == 3):
                    inputs, _, _, = data
                # if model is BiasedADM
                elif (len(data) == 5):
                    _, inputs, _, _, _= data

                inputs = inputs.to(self.device)

                # Zero the network parameter gradients
                optimizer.zero_grad()

                # Update network parameters via backpropagation: forward + backward + optimize
                rec = ae_net(inputs)
                rec_loss = criterion(rec, inputs)
                loss = torch.mean(rec_loss)
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item()
                n_batches += 1

            # log epoch statistics
            epoch_train_time = time.time() - epoch_start_time
            print(f'| Epoch: {epoch + 1:03}/{self.n_epochs:03} | Train Time: {epoch_train_time:.3f}s 'f'| Train Loss: {epoch_loss / n_batches:.6f} |')

        self.train_time = time.time() - start_time
        print('Pretraining Time: {:.3f}s'.format(self.train_time))
        print('Finished pretraining.')

        return ae_net

    def test(self, dataset, ae_net: BaseNet):
        logger = logging.getLogger()

        # Get test data loader
        _, test_loader = dataset.loaders(batch_size=self.batch_size, num_workers=self.n_jobs_dataloader)

        # Set loss
        criterion = nn.MSELoss(reduction='none')

        # Set device for network
        ae_net = ae_net.to(self.device)
        criterion = criterion.to(self.device)

        # Testing
        # print('Testing autoencoder...')
        epoch_loss = 0.0
        n_batches = 0
        start_time = time.time()
        idx_label_score = []
        ae_net.eval()
        with torch.no_grad():
            for data in test_loader:
                if (len(data) == 3):
                    inputs, labels, _ = data
                elif (len(data) == 5):
                    _, inputs, labels, _, _ = data

                inputs, labels = inputs.to(self.device), labels.to(self.device)

                rec = ae_net(inputs)
                rec_loss = criterion(rec, inputs)
                scores = torch.mean(rec_loss, dim=tuple(range(1, rec.dim())))

                # Save triple of (label, score) in a list
                idx_label_score += list(zip(labels.cpu().data.numpy().tolist(),
                                            scores.cpu().data.numpy().tolist()))

                loss = torch.mean(rec_loss)
                epoch_loss += loss.item()
                n_batches += 1

        self.test_time = time.time() - start_time

        # Compute AUROC and AUPRC
        labels, scores = zip(*idx_label_score)
        labels = np.array(labels)
        scores = np.array(scores)
        self.test_auc = roc_auc_score(labels, scores)
        precision, recall, threshold = precision_recall_curve(labels, scores)
        self.test_auc_pr = auc(recall, precision)
        
        # Log results
        print('Test Loss: {:.6f}'.format(epoch_loss / n_batches))
        print('Test AUC: {:.2f}%'.format(100. * self.test_auc))
        print('Test PRC: {:.2f}%'.format(100. * self.test_auc_pr))
        print('Test Time: {:.3f}s'.format(self.test_time))
        print('Finished testing autoencoder.')